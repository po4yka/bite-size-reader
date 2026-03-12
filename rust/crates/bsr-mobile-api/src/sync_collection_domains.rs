use std::collections::{BTreeMap, BTreeSet, HashMap};

use axum::extract::rejection::{JsonRejection, QueryRejection};
use axum::extract::{Json, Path, Query, State};
use axum::http::StatusCode;
use axum::response::Response;
use axum::routing::{get, post};
use axum::{Extension, Router};
use bsr_persistence::{
    accept_collection_invite, add_collection_collaborator, add_collection_item,
    apply_summary_sync_change, create_collection, create_collection_invite,
    get_collection_by_id, get_collection_owner_info, get_collection_role,
    get_next_collection_item_position, get_next_collection_position,
    get_summary_sync_entity_for_user, list_collection_collaborators,
    list_collection_items, list_collection_tree, list_collections_for_user,
    list_sync_entities_for_user, move_collection, move_collection_items,
    open_connection, remove_collection_collaborator, remove_collection_item,
    reorder_collection_items, reorder_collections, shift_collection_positions,
    soft_delete_collection, update_collection, CollectionAclRecord, CollectionItemRecord,
    CollectionRecord, MoveCollectionRecord, SyncEntityRecord,
};
use chrono::{Duration, Utc};
use rand::RngCore;
use redis::AsyncCommands;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

use crate::core_domains::CurrentUser;
use crate::{
    error_json_response, success_json_response, success_json_response_with_pagination,
    ApiRuntimeConfig, AppState, CorrelationId,
};

const COLLECTION_ROUTE_PATHS: [&str; 13] = [
    "/v1/collections",
    "/v1/collections/{collection_id}",
    "/v1/collections/{collection_id}/items",
    "/v1/collections/{collection_id}/items/{summary_id}",
    "/v1/collections/tree",
    "/v1/collections/{collection_id}/acl",
    "/v1/collections/{collection_id}/share",
    "/v1/collections/{collection_id}/share/{target_user_id}",
    "/v1/collections/{collection_id}/invite",
    "/v1/collections/invites/{token}/accept",
    "/v1/collections/{collection_id}/reorder",
    "/v1/collections/{collection_id}/items/reorder",
    "/v1/collections/{collection_id}/move",
];
const COLLECTION_ITEMS_MOVE_ROUTE: &str = "/v1/collections/{collection_id}/items/move";
const SYNC_ROUTE_PATHS: [&str; 4] = [
    "/v1/sync/sessions",
    "/v1/sync/full",
    "/v1/sync/delta",
    "/v1/sync/apply",
];

#[derive(Debug, Deserialize)]
struct CollectionListQuery {
    #[serde(default)]
    parent_id: Option<i64>,
    #[serde(default)]
    limit: Option<i64>,
    #[serde(default)]
    offset: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionItemsQuery {
    #[serde(default)]
    limit: Option<i64>,
    #[serde(default)]
    offset: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionTreeQuery {
    #[serde(default)]
    max_depth: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionCreatePayload {
    name: String,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    parent_id: Option<i64>,
    #[serde(default)]
    position: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionUpdatePayload {
    #[serde(default)]
    name: Option<String>,
    #[serde(default)]
    description: Option<String>,
    #[serde(default)]
    parent_id: Option<i64>,
    #[serde(default)]
    position: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionItemCreatePayload {
    summary_id: i64,
}

#[derive(Debug, Deserialize)]
struct CollectionMovePayload {
    #[serde(default)]
    parent_id: Option<i64>,
    #[serde(default)]
    position: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionItemMovePayload {
    summary_ids: Vec<i64>,
    target_collection_id: i64,
    #[serde(default)]
    position: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct CollectionSharePayload {
    user_id: i64,
    role: String,
}

#[derive(Debug, Deserialize)]
struct CollectionInvitePayload {
    role: String,
    #[serde(default)]
    expires_at: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CollectionReorderPayload {
    items: Vec<CollectionReorderItem>,
}

#[derive(Debug, Deserialize)]
struct CollectionReorderItem {
    collection_id: i64,
    position: i64,
}

#[derive(Debug, Deserialize)]
struct CollectionItemReorderPayload {
    items: Vec<CollectionItemReorderItem>,
}

#[derive(Debug, Deserialize)]
struct CollectionItemReorderItem {
    summary_id: i64,
    position: i64,
}

#[derive(Debug, Deserialize)]
struct SyncSessionRequestPayload {
    #[serde(default)]
    limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct SyncFullQuery {
    session_id: String,
    #[serde(default)]
    limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct SyncDeltaQuery {
    session_id: String,
    since: i64,
    #[serde(default)]
    limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
struct SyncApplyPayload {
    session_id: String,
    changes: Vec<SyncApplyItemPayload>,
}

#[derive(Debug, Deserialize)]
struct SyncApplyItemPayload {
    entity_type: String,
    id: Value,
    action: String,
    last_seen_version: i64,
    #[serde(default)]
    payload: Option<Map<String, Value>>,
    #[serde(default)]
    #[allow(dead_code)]
    client_timestamp: Option<String>,
}

#[derive(Debug, Deserialize)]
struct CollectionIdPath {
    collection_id: i64,
}

#[derive(Debug, Deserialize)]
struct CollectionItemPath {
    collection_id: i64,
    summary_id: i64,
}

#[derive(Debug, Deserialize)]
struct CollectionSharePath {
    collection_id: i64,
    target_user_id: i64,
}

#[derive(Debug, Deserialize)]
struct TokenPath {
    token: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SyncSessionPayload {
    session_id: String,
    user_id: i64,
    client_id: String,
    chunk_limit: i64,
    created_at: String,
    expires_at: String,
    next_since: i64,
}

pub(crate) fn build_router() -> Router<AppState> {
    Router::new()
        .route(
            "/v1/collections",
            get(list_collections_handler).post(create_collection_handler),
        )
        .route("/v1/collections/tree", get(get_collection_tree_handler))
        .route(
            "/v1/collections/{collection_id}",
            get(get_collection_handler)
                .patch(update_collection_handler)
                .delete(delete_collection_handler),
        )
        .route(
            "/v1/collections/{collection_id}/items",
            post(add_collection_item_handler).get(list_collection_items_handler),
        )
        .route(
            "/v1/collections/{collection_id}/items/{summary_id}",
            axum::routing::delete(remove_collection_item_handler),
        )
        .route(
            "/v1/collections/{collection_id}/items/reorder",
            post(reorder_collection_items_handler),
        )
        .route(
            "/v1/collections/{collection_id}/items/move",
            post(move_collection_items_handler),
        )
        .route(
            "/v1/collections/{collection_id}/reorder",
            post(reorder_collections_handler),
        )
        .route(
            "/v1/collections/{collection_id}/move",
            post(move_collection_handler),
        )
        .route(
            "/v1/collections/{collection_id}/acl",
            get(get_collection_acl_handler),
        )
        .route(
            "/v1/collections/{collection_id}/share",
            post(add_collection_collaborator_handler),
        )
        .route(
            "/v1/collections/{collection_id}/share/{target_user_id}",
            axum::routing::delete(remove_collection_collaborator_handler),
        )
        .route(
            "/v1/collections/{collection_id}/invite",
            post(create_collection_invite_handler),
        )
        .route(
            "/v1/collections/invites/{token}/accept",
            post(accept_collection_invite_handler),
        )
        .route("/v1/sync/sessions", post(create_sync_session_handler))
        .route("/v1/sync/full", get(full_sync_handler))
        .route("/v1/sync/delta", get(delta_sync_handler))
        .route("/v1/sync/apply", post(apply_sync_changes_handler))
}

pub(crate) fn implemented_route_map() -> BTreeMap<&'static str, BTreeSet<String>> {
    let mut routes = BTreeMap::new();
    routes.insert(COLLECTION_ROUTE_PATHS[0], set_of(["GET", "POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[1], set_of(["GET", "PATCH", "DELETE"]));
    routes.insert(COLLECTION_ROUTE_PATHS[2], set_of(["GET", "POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[3], set_of(["DELETE"]));
    routes.insert(COLLECTION_ROUTE_PATHS[4], set_of(["GET"]));
    routes.insert(COLLECTION_ROUTE_PATHS[5], set_of(["GET"]));
    routes.insert(COLLECTION_ROUTE_PATHS[6], set_of(["POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[7], set_of(["DELETE"]));
    routes.insert(COLLECTION_ROUTE_PATHS[8], set_of(["POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[9], set_of(["POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[10], set_of(["POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[11], set_of(["POST"]));
    routes.insert(COLLECTION_ROUTE_PATHS[12], set_of(["POST"]));
    routes.insert(COLLECTION_ITEMS_MOVE_ROUTE, set_of(["POST"]));
    routes.insert(SYNC_ROUTE_PATHS[0], set_of(["POST"]));
    routes.insert(SYNC_ROUTE_PATHS[1], set_of(["GET"]));
    routes.insert(SYNC_ROUTE_PATHS[2], set_of(["GET"]));
    routes.insert(SYNC_ROUTE_PATHS[3], set_of(["POST"]));
    routes
}

async fn list_collections_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<CollectionListQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if let Some(parent_id) = query.parent_id {
        if parent_id < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "parent_id", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }
    let limit = query.limit.unwrap_or(20);
    let offset = query.offset.unwrap_or(0);
    if !(1..=200).contains(&limit) || offset < 0 {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "limit", "message": "limit must be between 1 and 200"}]})),
        );
    }

    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let collections = match list_collections_for_user(
        &connection,
        user.user_id,
        query.parent_id,
        limit,
        offset,
    ) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };

    let payload = collections
        .iter()
        .map(|record| collection_to_value(record, None))
        .collect::<Vec<_>>();
    let pagination = json!({
        "total": payload.len(),
        "limit": limit,
        "offset": offset,
        "hasMore": payload.len() as i64 == limit,
    });
    success_json_response_with_pagination(
        json!({
            "collections": payload,
            "pagination": pagination,
        }),
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn create_collection_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    body: Result<Json<CollectionCreatePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if let Err(response) = validate_collection_name(body.name.as_str(), &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(response) = validate_collection_description(body.description.as_deref(), &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Some(parent_id) = body.parent_id {
        if parent_id < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "parent_id", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }
    if let Some(position) = body.position {
        if position < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "position", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }

    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };

    if let Some(parent_id) = body.parent_id {
        let parent = match get_collection_by_id(&connection, parent_id, false) {
            Ok(value) => value,
            Err(error) => {
                return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string())
            }
        };
        let Some(_) = parent else {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Collection",
                &parent_id.to_string(),
            );
        };
        if let Err(response) = require_collection_role(&connection, parent_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
            return response;
        }
    }

    let position = match body.position {
        Some(position) => {
            if let Err(error) = shift_collection_positions(&connection, body.parent_id, position) {
                return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
            }
            position
        }
        None => match get_next_collection_position(&connection, body.parent_id) {
            Ok(position) => position,
            Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
        },
    };

    let collection_id = match create_collection(
        &connection,
        user.user_id,
        body.name.as_str(),
        body.description.as_deref(),
        body.parent_id,
        position,
    ) {
        Ok(collection_id) => collection_id,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let collection = match get_collection_by_id(&connection, collection_id, false) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Collection",
                &collection_id.to_string(),
            )
        }
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    success_json_response(
        collection_to_value(&collection, None),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_collection_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let Some(collection) = (match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "viewer", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    success_json_response(
        collection_to_value(&collection, None),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn update_collection_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionUpdatePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if let Some(name) = body.name.as_deref() {
        if let Err(response) = validate_collection_name(name, &correlation_id.0, &state.runtime.config) {
            return response;
        }
    }
    if let Err(response) = validate_collection_description(body.description.as_deref(), &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Some(position) = body.position {
        if position < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "position", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }
    if let Some(parent_id) = body.parent_id {
        if parent_id < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "parent_id", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }

    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let Some(existing) = (match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if body.parent_id == Some(path.collection_id) {
        return bad_request_response(
            &correlation_id.0,
            &state.runtime.config,
            "Cannot set collection as its own parent",
        );
    }

    let mut update_parent = None;
    let mut update_position = body.position;
    if let Some(parent_id) = body.parent_id {
        if Some(parent_id) != existing.parent_id {
            let parent = match get_collection_by_id(&connection, parent_id, false) {
                Ok(value) => value,
                Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
            };
            let Some(_) = parent else {
                return resource_not_found_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Collection",
                    &parent_id.to_string(),
                );
            };
            if let Err(response) = require_collection_role(&connection, parent_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
                return response;
            }
            update_parent = Some(parent_id);
            if update_position.is_none() {
                update_position = match get_next_collection_position(&connection, Some(parent_id)) {
                    Ok(position) => Some(position),
                    Err(error) => {
                        return database_unavailable_response(
                            &correlation_id.0,
                            &state.runtime.config,
                            &error.to_string(),
                        )
                    }
                };
            }
        }
    }

    let target_parent = update_parent.or(existing.parent_id);
    if let Some(position) = update_position {
        if let Err(error) = shift_collection_positions(&connection, target_parent, position) {
            return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
        }
    }

    if let Err(error) = update_collection(
        &connection,
        path.collection_id,
        body.name.as_deref(),
        body.description.as_deref(),
        update_parent,
        update_position,
    ) {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
    }
    let updated = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Collection",
                &path.collection_id.to_string(),
            )
        }
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    success_json_response(
        collection_to_value(&updated, None),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn delete_collection_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let exists = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if exists.is_none() {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    }
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "owner", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(error) = soft_delete_collection(&connection, path.collection_id) {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn add_collection_item_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionItemCreatePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let position = match get_next_collection_item_position(&connection, path.collection_id) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let added = match add_collection_item(&connection, path.collection_id, body.summary_id, position) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if !added {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Summary",
            &body.summary_id.to_string(),
        );
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn list_collection_items_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    query: Result<Query<CollectionItemsQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    let limit = query.limit.unwrap_or(50);
    let offset = query.offset.unwrap_or(0);
    if !(1..=200).contains(&limit) || offset < 0 {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "limit", "message": "limit must be between 1 and 200"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "viewer", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let items = match list_collection_items(&connection, path.collection_id, limit, offset) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let payload = items.iter().map(collection_item_to_value).collect::<Vec<_>>();
    let pagination = json!({
        "total": payload.len(),
        "limit": limit,
        "offset": offset,
        "hasMore": payload.len() as i64 == limit,
    });
    success_json_response_with_pagination(
        json!({
            "items": payload,
            "pagination": pagination,
        }),
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn remove_collection_item_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionItemPath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(error) = remove_collection_item(&connection, path.collection_id, path.summary_id) {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn reorder_collection_items_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionItemReorderPayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if body.items.is_empty() {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "items", "message": "List should have at least 1 item after validation, not 0"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let item_positions = body
        .items
        .iter()
        .map(|item| (item.summary_id, item.position))
        .collect::<Vec<_>>();
    if let Err(error) = reorder_collection_items(&connection, path.collection_id, &item_positions) {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn move_collection_items_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionItemMovePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if body.summary_ids.is_empty() {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "summary_ids", "message": "List should have at least 1 item after validation, not 0"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(response) = require_collection_role(&connection, body.target_collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let moved = match move_collection_items(
        &connection,
        path.collection_id,
        body.target_collection_id,
        &body.summary_ids,
        body.position,
    ) {
        Ok(result) => result,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    success_json_response(
        json!({"movedSummaryIds": moved.moved_summary_ids}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn reorder_collections_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionReorderPayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if body.items.is_empty() {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "items", "message": "List should have at least 1 item after validation, not 0"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let positions = body
        .items
        .iter()
        .map(|item| (item.collection_id, item.position))
        .collect::<Vec<_>>();
    if let Err(error) = reorder_collections(&connection, Some(path.collection_id), &positions) {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn move_collection_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionMovePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if let Some(position) = body.position {
        if position < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "position", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }
    if let Some(parent_id) = body.parent_id {
        if parent_id < 1 {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "parent_id", "message": "Input should be greater than or equal to 1"}]})),
            );
        }
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let exists = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if exists.is_none() {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    }
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "owner", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Some(parent_id) = body.parent_id {
        let parent = match get_collection_by_id(&connection, parent_id, false) {
            Ok(value) => value,
            Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
        };
        let Some(_) = parent else {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Collection",
                &parent_id.to_string(),
            );
        };
        if let Err(response) = require_collection_role(&connection, parent_id, user.user_id, "editor", &correlation_id.0, &state.runtime.config) {
            return response;
        }
    }
    let position = match body.position {
        Some(value) => value,
        None => match get_next_collection_position(&connection, body.parent_id) {
            Ok(value) => value,
            Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
        },
    };
    let moved = match move_collection(&connection, path.collection_id, body.parent_id, position) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return bad_request_response(
                &correlation_id.0,
                &state.runtime.config,
                "Cycle detected or collection not found",
            )
        }
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    success_json_response(
        move_collection_to_value(&moved),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_collection_tree_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<CollectionTreeQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    let max_depth = query.max_depth.unwrap_or(3);
    if !(1..=10).contains(&max_depth) {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "max_depth", "message": "max_depth must be between 1 and 10"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let records = match list_collection_tree(&connection, user.user_id) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let trees = build_collection_tree(records, max_depth as usize);
    success_json_response(
        json!({"collections": trees}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_collection_acl_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let exists = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if exists.is_none() {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    }
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "viewer", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let mut acl = Vec::new();
    if let Ok(Some(owner)) = get_collection_owner_info(&connection, path.collection_id) {
        acl.push(collection_acl_to_value(&owner));
    }
    let collaborators = match list_collection_collaborators(&connection, path.collection_id) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    acl.extend(collaborators.iter().map(collection_acl_to_value));
    success_json_response(json!({"acl": acl}), correlation_id.0, &state.runtime.config)
}

async fn add_collection_collaborator_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionSharePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if !matches!(body.role.as_str(), "editor" | "viewer") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "role", "message": "role must be editor or viewer"}]})),
        );
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let collection = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let Some(collection) = collection else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "owner", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if body.user_id != collection.user_id {
        if let Err(error) = add_collection_collaborator(
            &connection,
            path.collection_id,
            body.user_id,
            body.role.as_str(),
            Some(user.user_id),
        ) {
            return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
        }
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn remove_collection_collaborator_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionSharePath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let collection = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let Some(collection) = collection else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    };
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "owner", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    if path.target_user_id != collection.user_id {
        if let Err(error) = remove_collection_collaborator(&connection, path.collection_id, path.target_user_id) {
            return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string());
        }
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn create_collection_invite_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<CollectionIdPath>,
    body: Result<Json<CollectionInvitePayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if !matches!(body.role.as_str(), "editor" | "viewer") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "role", "message": "role must be editor or viewer"}]})),
        );
    }
    if let Some(expires_at) = body.expires_at.as_deref() {
        if expires_at.trim().is_empty() || chrono::DateTime::parse_from_rfc3339(expires_at).is_err() {
            return bad_request_response(&correlation_id.0, &state.runtime.config, "Invalid expires_at");
        }
    }
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let collection = match get_collection_by_id(&connection, path.collection_id, false) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if collection.is_none() {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Collection",
            &path.collection_id.to_string(),
        );
    }
    if let Err(response) = require_collection_role(&connection, path.collection_id, user.user_id, "owner", &correlation_id.0, &state.runtime.config) {
        return response;
    }
    let invite = match create_collection_invite(
        &connection,
        path.collection_id,
        body.role.as_str(),
        body.expires_at.as_deref(),
    ) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Collection",
                &path.collection_id.to_string(),
            )
        }
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    success_json_response(
        json!({
            "token": invite.token,
            "role": invite.role,
            "expiresAt": body.expires_at,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn accept_collection_invite_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    Path(path): Path<TokenPath>,
) -> Response {
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let accepted = match accept_collection_invite(&connection, path.token.as_str(), user.user_id) {
        Ok(value) => value,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    if accepted.is_none() {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Invite",
            path.token.as_str(),
        );
    }
    success_json_response(json!({"success": true}), correlation_id.0, &state.runtime.config)
}

async fn create_sync_session_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    body: Result<Option<Json<SyncSessionRequestPayload>>, JsonRejection>,
) -> Response {
    let body = match body {
        Ok(value) => value.map(|json| json.0),
        Err(err) => {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "body", "message": err.body_text()}]})),
            )
        }
    };
    let requested_limit = body.as_ref().and_then(|payload| payload.limit);
    if let Some(limit) = requested_limit {
        if !(1..=500).contains(&limit) {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "limit", "message": "limit must be between 1 and 500"}]})),
            );
        }
    }
    let resolved_limit = resolve_sync_limit(requested_limit, &state.runtime.config);
    let now = Utc::now();
    let expires_at = now + Duration::hours(state.runtime.config.sync_expiry_hours.max(1));
    let payload = SyncSessionPayload {
        session_id: format!("sync-{}", random_hex(8)),
        user_id: user.user_id,
        client_id: user.client_id.clone(),
        chunk_limit: resolved_limit,
        created_at: now.to_rfc3339().replace("+00:00", "Z"),
        expires_at: expires_at.to_rfc3339().replace("+00:00", "Z"),
        next_since: 0,
    };
    if let Err(error) = store_sync_session(&state, &payload).await {
        return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error);
    }
    let pagination = json!({
        "total": 0,
        "limit": state.runtime.config.sync_default_limit,
        "offset": 0,
        "hasMore": true,
    });
    success_json_response_with_pagination(
        json!({
            "sessionId": payload.session_id,
            "expiresAt": payload.expires_at,
            "defaultLimit": state.runtime.config.sync_default_limit,
            "maxLimit": state.runtime.config.sync_max_limit,
            "lastIssuedSince": 0,
        }),
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn full_sync_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<SyncFullQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if let Some(limit) = query.limit {
        if !(1..=500).contains(&limit) {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "limit", "message": "limit must be between 1 and 500"}]})),
            );
        }
    }
    let session = match load_sync_session(&state, query.session_id.as_str(), user.user_id, user.client_id.as_str()).await {
        Ok(payload) => payload,
        Err(response) => return response,
    };
    let limit = resolve_sync_limit(query.limit.or(Some(session.chunk_limit)), &state.runtime.config);
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let records = match list_sync_entities_for_user(&connection, user.user_id) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let page = records.into_iter().take(limit as usize).collect::<Vec<_>>();
    let next_since = page.last().map(|record| record.server_version).unwrap_or(0);
    let has_more = page.len() as i64 == limit;
    let pagination = json!({
        "total": page.len(),
        "limit": limit,
        "offset": 0,
        "hasMore": has_more,
    });
    success_json_response_with_pagination(
        json!({
            "sessionId": session.session_id,
            "hasMore": has_more,
            "nextSince": next_since,
            "items": page.iter().map(sync_entity_to_value).collect::<Vec<_>>(),
            "pagination": pagination,
        }),
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn delta_sync_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<SyncDeltaQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    if query.since < 0 {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "since", "message": "since must be greater than or equal to 0"}]})),
        );
    }
    if let Some(limit) = query.limit {
        if !(1..=500).contains(&limit) {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"fields": [{"field": "limit", "message": "limit must be between 1 and 500"}]})),
            );
        }
    }
    let session = match load_sync_session(&state, query.session_id.as_str(), user.user_id, user.client_id.as_str()).await {
        Ok(payload) => payload,
        Err(response) => return response,
    };
    let limit = resolve_sync_limit(query.limit.or(Some(session.chunk_limit)), &state.runtime.config);
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };
    let records = match list_sync_entities_for_user(&connection, user.user_id) {
        Ok(records) => records,
        Err(error) => return database_unavailable_response(&correlation_id.0, &state.runtime.config, &error.to_string()),
    };
    let filtered = records
        .into_iter()
        .filter(|record| record.server_version > query.since)
        .collect::<Vec<_>>();
    let has_more = filtered.len() as i64 > limit;
    let page = filtered.into_iter().take(limit as usize).collect::<Vec<_>>();
    let next_since = page.last().map(|record| record.server_version).unwrap_or(query.since);
    let created = page
        .iter()
        .filter(|record| record.deleted_at.is_none())
        .map(sync_entity_to_value)
        .collect::<Vec<_>>();
    let deleted = page
        .iter()
        .filter(|record| record.deleted_at.is_some())
        .map(sync_entity_to_value)
        .collect::<Vec<_>>();
    let pagination = json!({
        "total": created.len() + deleted.len(),
        "limit": limit,
        "offset": 0,
        "hasMore": has_more,
    });
    success_json_response_with_pagination(
        json!({
            "sessionId": session.session_id,
            "since": query.since,
            "hasMore": has_more,
            "nextSince": next_since,
            "created": created,
            "updated": Vec::<Value>::new(),
            "deleted": deleted,
        }),
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn apply_sync_changes_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    body: Result<Json<SyncApplyPayload>, JsonRejection>,
) -> Response {
    let body = match parse_json_body(body, &correlation_id.0, &state.runtime.config) {
        Ok(value) => value.0,
        Err(response) => return response,
    };
    let _session = match load_sync_session(&state, body.session_id.as_str(), user.user_id, user.client_id.as_str()).await {
        Ok(payload) => payload,
        Err(response) => return response,
    };
    let connection = match open_db(&state, &correlation_id.0) {
        Ok(connection) => connection,
        Err(response) => return response,
    };

    let mut results = Vec::new();
    let mut conflicts = Vec::new();
    for change in &body.changes {
        if change.last_seen_version < 0 {
            results.push(json!({
                "entityType": change.entity_type,
                "id": change.id,
                "status": "invalid",
                "serverVersion": Value::Null,
                "serverSnapshot": Value::Null,
                "errorCode": "INVALID_VERSION",
            }));
            continue;
        }
        if change.entity_type != "summary" {
            results.push(json!({
                "entityType": change.entity_type,
                "id": change.id,
                "status": "invalid",
                "serverVersion": Value::Null,
                "serverSnapshot": Value::Null,
                "errorCode": "UNSUPPORTED_ENTITY",
            }));
            continue;
        }
        let summary_id = match change.id.as_i64() {
            Some(value) => value,
            None => {
                results.push(json!({
                    "entityType": change.entity_type,
                    "id": change.id,
                    "status": "invalid",
                    "serverVersion": Value::Null,
                    "serverSnapshot": Value::Null,
                    "errorCode": "INVALID_ID",
                }));
                continue;
            }
        };
        let summary = match get_summary_sync_entity_for_user(&connection, summary_id, user.user_id) {
            Ok(value) => value,
            Err(error) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &error.to_string(),
                )
            }
        };
        let Some(summary) = summary else {
            results.push(json!({
                "entityType": change.entity_type,
                "id": change.id,
                "status": "invalid",
                "serverVersion": Value::Null,
                "serverSnapshot": Value::Null,
                "errorCode": "NOT_FOUND",
            }));
            continue;
        };
        if change.last_seen_version < summary.server_version {
            let conflict = json!({
                "entityType": change.entity_type,
                "id": change.id,
                "status": "conflict",
                "serverVersion": summary.server_version,
                "serverSnapshot": sync_entity_to_value(&summary),
                "errorCode": "CONFLICT_VERSION",
            });
            conflicts.push(conflict.clone());
            results.push(conflict);
            continue;
        }
        let payload = change.payload.as_ref().cloned().unwrap_or_default();
        let invalid_fields = payload
            .keys()
            .filter(|field| field.as_str() != "is_read")
            .cloned()
            .collect::<Vec<_>>();
        if !invalid_fields.is_empty() {
            results.push(json!({
                "entityType": change.entity_type,
                "id": change.id,
                "status": "invalid",
                "serverVersion": summary.server_version,
                "serverSnapshot": Value::Null,
                "errorCode": "INVALID_FIELDS",
            }));
            continue;
        }

        let is_deleted = if change.action == "delete" {
            Some(true)
        } else {
            None
        };
        let deleted_at = if change.action == "delete" {
            Some(Utc::now().to_rfc3339())
        } else {
            None
        };
        let is_read = payload.get("is_read").and_then(Value::as_bool);
        let server_version = match apply_summary_sync_change(
            &connection,
            summary_id,
            is_deleted,
            deleted_at.as_deref(),
            is_read,
        ) {
            Ok(value) => value,
            Err(error) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &error.to_string(),
                )
            }
        };
        results.push(json!({
            "entityType": change.entity_type,
            "id": change.id,
            "status": "applied",
            "serverVersion": server_version,
            "serverSnapshot": Value::Null,
            "errorCode": Value::Null,
        }));
    }

    success_json_response(
        json!({
            "sessionId": body.session_id,
            "results": results,
            "conflicts": if conflicts.is_empty() { Value::Null } else { Value::Array(conflicts) },
            "hasMore": Value::Null,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

fn collection_to_value(record: &CollectionRecord, children: Option<Vec<Value>>) -> Value {
    json!({
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "parentId": record.parent_id,
        "position": record.position,
        "createdAt": python_like_iso_text(record.created_at.as_deref()),
        "updatedAt": python_like_iso_text(record.updated_at.as_deref()),
        "serverVersion": record.server_version.unwrap_or_default(),
        "isShared": record.is_shared,
        "shareCount": record.share_count,
        "itemCount": record.item_count,
        "children": children,
    })
}

fn collection_item_to_value(record: &CollectionItemRecord) -> Value {
    json!({
        "collectionId": record.collection_id,
        "summaryId": record.summary_id,
        "position": record.position,
        "createdAt": python_like_iso_text(record.created_at.as_deref()),
    })
}

fn collection_acl_to_value(record: &CollectionAclRecord) -> Value {
    json!({
        "userId": if record.role == "owner" { json!(record.user_id) } else { Value::Null },
        "role": record.role,
        "status": record.status,
        "invitedBy": record.invited_by,
        "createdAt": record.created_at.as_deref().map(|value| python_like_iso_text(Some(value))),
        "updatedAt": record.updated_at.as_deref().map(|value| python_like_iso_text(Some(value))),
    })
}

fn move_collection_to_value(record: &MoveCollectionRecord) -> Value {
    json!({
        "id": record.id,
        "parentId": record.parent_id,
        "position": record.position,
        "serverVersion": record.server_version,
        "updatedAt": python_like_iso_text(record.updated_at.as_deref()),
    })
}

fn sync_entity_to_value(record: &SyncEntityRecord) -> Value {
    json!({
        "entityType": record.entity_type,
        "id": record.id,
        "serverVersion": record.server_version,
        "updatedAt": record.updated_at,
        "deletedAt": record.deleted_at,
        "summary": record.summary,
        "request": record.request,
        "preference": record.preference,
        "stat": record.stat,
        "crawlResult": record.crawl_result,
        "llmCall": record.llm_call,
    })
}

fn build_collection_tree(records: Vec<CollectionRecord>, max_depth: usize) -> Vec<Value> {
    let mut by_parent: BTreeMap<Option<i64>, Vec<CollectionRecord>> = BTreeMap::new();
    for record in records {
        by_parent.entry(record.parent_id).or_default().push(record);
    }
    for records in by_parent.values_mut() {
        records.sort_by(|left, right| {
            left.position
                .cmp(&right.position)
                .then_with(|| left.created_at.cmp(&right.created_at))
        });
    }

    fn build(
        by_parent: &BTreeMap<Option<i64>, Vec<CollectionRecord>>,
        parent_id: Option<i64>,
        depth: usize,
        max_depth: usize,
    ) -> Vec<Value> {
        if depth > max_depth {
            return Vec::new();
        }
        by_parent
            .get(&parent_id)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .map(|record| {
                let children = build(by_parent, Some(record.id), depth + 1, max_depth);
                collection_to_value(
                    &record,
                    if children.is_empty() {
                        Some(Vec::new())
                    } else {
                        Some(children)
                    },
                )
            })
            .collect()
    }

    build(&by_parent, None, 1, max_depth)
}

fn role_rank(role: &str) -> i32 {
    match role {
        "owner" => 3,
        "editor" => 2,
        "viewer" => 1,
        _ => 0,
    }
}

fn require_collection_role(
    connection: &rusqlite::Connection,
    collection_id: i64,
    user_id: i64,
    minimum_role: &str,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<String, Response> {
    let role = get_collection_role(connection, collection_id, user_id).map_err(|error| {
        database_unavailable_response(correlation_id, config, &error.to_string())
    })?;
    let Some(role) = role else {
        return Err(forbidden_response(
            correlation_id,
            config,
            &format!("Insufficient permissions for collection {collection_id}"),
        ));
    };
    if role_rank(role.as_str()) < role_rank(minimum_role) {
        return Err(forbidden_response(
            correlation_id,
            config,
            &format!("Insufficient permissions for collection {collection_id}"),
        ));
    }
    Ok(role)
}

fn resolve_sync_limit(requested: Option<i64>, config: &ApiRuntimeConfig) -> i64 {
    requested
        .unwrap_or(config.sync_default_limit)
        .max(config.sync_min_limit)
        .min(config.sync_max_limit)
}

async fn store_sync_session(state: &AppState, payload: &SyncSessionPayload) -> Result<(), String> {
    let serialized = serde_json::to_string(payload).map_err(|error| error.to_string())?;
    if let Some(mut redis) = redis_connection(&state.runtime.config).await {
        let key = sync_session_key(&state.runtime.config, payload.session_id.as_str());
        let ttl = (state.runtime.config.sync_expiry_hours * 3600).max(1);
        let _ = redis
            .set_ex::<_, _, ()>(key, serialized.clone(), ttl as u64)
            .await;
    }
    let mut sessions = state.runtime.local_sync_sessions.lock().await;
    prune_local_sync_sessions(&mut sessions);
    sessions.insert(payload.session_id.clone(), serde_json::to_value(payload).map_err(|error| error.to_string())?);
    Ok(())
}

async fn load_sync_session(
    state: &AppState,
    session_id: &str,
    user_id: i64,
    client_id: &str,
) -> Result<SyncSessionPayload, Response> {
    if let Some(mut redis) = redis_connection(&state.runtime.config).await {
        let key = sync_session_key(&state.runtime.config, session_id);
        if let Ok(Some(raw)) = redis.get::<_, Option<String>>(key.clone()).await {
            if let Ok(payload) = serde_json::from_str::<SyncSessionPayload>(&raw) {
                return validate_sync_session(payload, user_id, client_id, &state.runtime.config);
            }
        }
    }

    let mut sessions = state.runtime.local_sync_sessions.lock().await;
    prune_local_sync_sessions(&mut sessions);
    let Some(raw) = sessions.get(session_id).cloned() else {
        return Err(sync_not_found_response(session_id, &state.runtime.config));
    };
    let payload: SyncSessionPayload = serde_json::from_value(raw).map_err(|_| {
        sync_not_found_response(session_id, &state.runtime.config)
    })?;
    if sync_session_expired(&payload) {
        sessions.remove(session_id);
        return Err(sync_expired_response(session_id, &state.runtime.config));
    }
    validate_sync_session(payload, user_id, client_id, &state.runtime.config)
}

fn validate_sync_session(
    payload: SyncSessionPayload,
    user_id: i64,
    client_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<SyncSessionPayload, Response> {
    if payload.user_id != user_id || payload.client_id != client_id {
        return Err(sync_forbidden_response(config));
    }
    if sync_session_expired(&payload) {
        return Err(sync_expired_response(payload.session_id.as_str(), config));
    }
    Ok(payload)
}

fn sync_session_expired(payload: &SyncSessionPayload) -> bool {
    chrono::DateTime::parse_from_rfc3339(payload.expires_at.as_str())
        .map(|value| value.with_timezone(&Utc) <= Utc::now())
        .unwrap_or(false)
}

fn prune_local_sync_sessions(sessions: &mut HashMap<String, Value>) {
    let expired = sessions
        .iter()
        .filter_map(|(session_id, raw)| {
            serde_json::from_value::<SyncSessionPayload>(raw.clone())
                .ok()
                .and_then(|payload| sync_session_expired(&payload).then_some(session_id.clone()))
        })
        .collect::<Vec<_>>();
    for session_id in expired {
        sessions.remove(session_id.as_str());
    }
}

async fn redis_connection(
    config: &ApiRuntimeConfig,
) -> Option<redis::aio::MultiplexedConnection> {
    if !config.redis_enabled {
        return None;
    }
    let client = if let Some(url) = config.redis_url.as_deref() {
        redis::Client::open(url).ok()?
    } else if let Some(password) = config.redis_password.as_deref() {
        redis::Client::open(format!(
            "redis://:{}@{}:{}/{}",
            password, config.redis_host, config.redis_port, config.redis_db
        ))
        .ok()?
    } else {
        redis::Client::open(format!(
            "redis://{}:{}/{}",
            config.redis_host, config.redis_port, config.redis_db
        ))
        .ok()?
    };
    client.get_multiplexed_async_connection().await.ok()
}

fn sync_session_key(config: &ApiRuntimeConfig, session_id: &str) -> String {
    format!("{}:sync:session:{session_id}", config.redis_prefix)
}

fn parse_json_body<T: DeserializeOwned>(
    payload: Result<Json<T>, JsonRejection>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<Json<T>, Response> {
    payload.map_err(|err| {
        validation_error_response(
            correlation_id,
            config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "body", "message": err.body_text()}]})),
        )
    })
}

fn parse_query<T: DeserializeOwned>(
    payload: Result<Query<T>, QueryRejection>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<Query<T>, Response> {
    payload.map_err(|err| {
        validation_error_response(
            correlation_id,
            config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "query", "message": err.body_text()}]})),
        )
    })
}

fn validate_collection_name(
    name: &str,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if name.trim().is_empty() || name.len() > 100 {
        return Err(validation_error_response(
            correlation_id,
            config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "name", "message": "name must be between 1 and 100 characters"}]})),
        ));
    }
    Ok(())
}

fn validate_collection_description(
    description: Option<&str>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if description.is_some_and(|value| value.len() > 500) {
        return Err(validation_error_response(
            correlation_id,
            config,
            "Request validation failed",
            Some(json!({"fields": [{"field": "description", "message": "description must be at most 500 characters"}]})),
        ));
    }
    Ok(())
}

fn open_db(state: &AppState, correlation_id: &str) -> Result<rusqlite::Connection, Response> {
    open_connection(&state.runtime.config.db_path).map_err(|error| {
        database_unavailable_response(correlation_id, &state.runtime.config, &error.to_string())
    })
}

fn validation_error_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
    details: Option<Value>,
) -> Response {
    error_json_response(
        StatusCode::UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        message,
        "validation",
        false,
        correlation_id.to_string(),
        config,
        details,
        None,
        Vec::new(),
    )
}

fn resource_not_found_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    resource_type: &str,
    resource_id: &str,
) -> Response {
    error_json_response(
        StatusCode::NOT_FOUND,
        "NOT_FOUND",
        &format!("{resource_type} with ID {resource_id} not found"),
        "not_found",
        false,
        correlation_id.to_string(),
        config,
        Some(json!({"resource_type": resource_type, "resource_id": resource_id})),
        None,
        Vec::new(),
    )
}

fn forbidden_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
) -> Response {
    error_json_response(
        StatusCode::FORBIDDEN,
        "FORBIDDEN",
        message,
        "authorization",
        false,
        correlation_id.to_string(),
        config,
        None,
        None,
        Vec::new(),
    )
}

fn bad_request_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
) -> Response {
    error_json_response(
        StatusCode::BAD_REQUEST,
        "VALIDATION_ERROR",
        message,
        "validation",
        false,
        correlation_id.to_string(),
        config,
        None,
        None,
        Vec::new(),
    )
}

fn database_unavailable_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    reason: &str,
) -> Response {
    error_json_response(
        StatusCode::SERVICE_UNAVAILABLE,
        "DATABASE_ERROR",
        "Database temporarily unavailable",
        "internal",
        true,
        correlation_id.to_string(),
        config,
        Some(json!({"reason": reason})),
        None,
        Vec::new(),
    )
}

fn sync_not_found_response(session_id: &str, config: &ApiRuntimeConfig) -> Response {
    error_json_response(
        StatusCode::NOT_FOUND,
        "SYNC_SESSION_NOT_FOUND",
        "Sync session not found. Please start a new sync session.",
        "sync",
        true,
        String::new(),
        config,
        Some(json!({"session_id": session_id})),
        None,
        Vec::new(),
    )
}

fn sync_expired_response(session_id: &str, config: &ApiRuntimeConfig) -> Response {
    error_json_response(
        StatusCode::GONE,
        "SYNC_SESSION_EXPIRED",
        "Sync session expired. Please start a new sync session.",
        "sync",
        true,
        String::new(),
        config,
        Some(json!({"session_id": session_id})),
        None,
        Vec::new(),
    )
}

fn sync_forbidden_response(config: &ApiRuntimeConfig) -> Response {
    error_json_response(
        StatusCode::FORBIDDEN,
        "SYNC_SESSION_FORBIDDEN",
        "Sync session does not belong to this user or client.",
        "sync",
        false,
        String::new(),
        config,
        None,
        None,
        Vec::new(),
    )
}

fn python_like_iso_text(value: Option<&str>) -> String {
    match value {
        Some(raw) if raw.ends_with('Z') => raw.to_string(),
        Some(raw) => match chrono::DateTime::parse_from_rfc3339(raw).ok() {
            Some(parsed) => parsed
                .with_timezone(&Utc)
                .to_rfc3339()
                .replace("+00:00", "Z"),
            None if !raw.trim().is_empty() => format!("{raw}Z"),
            None => Utc::now().to_rfc3339().replace("+00:00", "Z"),
        },
        None => Utc::now().to_rfc3339().replace("+00:00", "Z"),
    }
}

fn set_of<const N: usize>(methods: [&str; N]) -> BTreeSet<String> {
    methods.into_iter().map(str::to_string).collect()
}

fn random_hex(bytes_len: usize) -> String {
    let mut bytes = vec![0_u8; bytes_len];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
