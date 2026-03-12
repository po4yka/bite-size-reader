use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::env;
use std::io::ErrorKind;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::{Path, PathBuf};
use std::time::Instant;

use axum::body::Body;
use axum::extract::rejection::{JsonRejection, QueryRejection};
use axum::extract::{Path as AxumPath, Query, State};
use axum::http::header::{
    CACHE_CONTROL, CONTENT_DISPOSITION, CONTENT_LENGTH, CONTENT_TYPE, LOCATION,
};
use axum::http::{HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Extension, Json, Router};
use bsr_persistence::{
    complete_audio_generation, count_pending_requests_before, create_request,
    fail_audio_generation, get_audio_generation_by_summary, get_crawl_result_by_request_api,
    get_latest_llm_call_by_request, get_request_by_dedupe_hash, get_request_by_id_for_user,
    get_summary_by_id_for_user, get_summary_by_request_id, get_summary_id_by_url_for_user,
    list_llm_calls_by_request, list_user_summaries, mark_summary_as_read, mark_summary_as_unread,
    normalize_datetime_text, open_connection, soft_delete_summary, start_audio_generation,
    toggle_summary_favorite, update_request_error, upsert_user_device, ApiRequestRecord,
    ApiSummaryRecord, CreateRequestInput, RequestErrorUpdate, SummaryListFilters,
};
use bsr_processing_orchestrator::{
    execute_forward_flow, execute_url_flow, ForwardExecuteInput, OrchestratorEvent, UrlExecuteInput,
};
use chrono::Utc;
use reqwest::redirect::Policy;
use reqwest::Client;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio::fs;
use url::{form_urlencoded, Url};

use crate::core_domains::CurrentUser;
use crate::{
    error_json_response, success_json_response, success_json_response_with_pagination,
    ApiRuntimeConfig, AppState, CorrelationId,
};

const SUMMARY_ROUTE_PATHS: [&str; 6] = [
    "/v1/summaries",
    "/v1/summaries/by-url",
    "/v1/summaries/{summary_id}",
    "/v1/summaries/{summary_id}/content",
    "/v1/summaries/{summary_id}/favorite",
    "/v1/summaries/{summary_id}/audio",
];
const ARTICLE_ROUTE_PATHS: [&str; 5] = [
    "/v1/articles",
    "/v1/articles/by-url",
    "/v1/articles/{summary_id}",
    "/v1/articles/{summary_id}/content",
    "/v1/articles/{summary_id}/favorite",
];
const TRACKING_PARAMS: &[&str] = &[
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
];
const MAX_PROXY_RESPONSE_BYTES: usize = 10 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
enum SubmitRequestPayload {
    Url {
        input_url: String,
        #[serde(default = "default_language")]
        lang_preference: String,
    },
    Forward {
        content_text: String,
        forward_metadata: ForwardMetadata,
        #[serde(default = "default_language")]
        lang_preference: String,
    },
}

#[derive(Debug, Deserialize, Clone)]
struct ForwardMetadata {
    from_chat_id: i64,
    from_message_id: i64,
    #[serde(default)]
    from_chat_title: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SummaryListQuery {
    #[serde(default)]
    limit: Option<i64>,
    #[serde(default)]
    offset: Option<i64>,
    #[serde(default)]
    is_read: Option<bool>,
    #[serde(default)]
    is_favorited: Option<bool>,
    #[serde(default)]
    lang: Option<String>,
    #[serde(default)]
    start_date: Option<String>,
    #[serde(default)]
    end_date: Option<String>,
    #[serde(default)]
    sort: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SummaryByUrlQuery {
    url: String,
}

#[derive(Debug, Deserialize)]
struct SummaryContentQuery {
    #[serde(default)]
    format: Option<String>,
}

#[derive(Debug, Deserialize)]
struct UpdateSummaryPayload {
    #[serde(default)]
    is_read: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct DeviceRegistrationPayload {
    token: String,
    platform: String,
    #[serde(default)]
    device_id: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ProxyQuery {
    url: String,
}

#[derive(Debug, Deserialize)]
struct TtsQuery {
    #[serde(default)]
    source_field: Option<String>,
}

#[derive(Debug, Clone)]
struct ApiRequestExecutionConfig {
    prompt_version: String,
    enable_chunking: bool,
    chunk_max_chars: usize,
    primary_model: String,
    long_context_model: Option<String>,
    fallback_models: Vec<String>,
    flash_model: Option<String>,
    flash_fallback_models: Vec<String>,
    structured_output_mode: String,
    temperature: f64,
    top_p: Option<f64>,
    json_temperature: Option<f64>,
    json_top_p: Option<f64>,
    enable_two_pass_enrichment: bool,
    execute_inline: bool,
}

#[derive(Debug, Clone)]
struct TtsRuntimeConfig {
    enabled: bool,
    api_key: Option<String>,
    voice_id: String,
    model: String,
    output_format: String,
    stability: f64,
    similarity_boost: f64,
    speed: f64,
    timeout_sec: f64,
    max_chars_per_request: usize,
    audio_storage_path: PathBuf,
    base_url: String,
}

pub(crate) fn build_router() -> Router<AppState> {
    Router::new()
        .route("/v1/summaries", get(list_summaries_handler))
        .route("/v1/summaries/by-url", get(get_summary_by_url_handler))
        .route(
            "/v1/summaries/{summary_id}",
            get(get_summary_handler)
                .patch(update_summary_handler)
                .delete(delete_summary_handler),
        )
        .route(
            "/v1/summaries/{summary_id}/content",
            get(get_summary_content_handler),
        )
        .route(
            "/v1/summaries/{summary_id}/favorite",
            post(toggle_favorite_handler),
        )
        .route(
            "/v1/summaries/{summary_id}/audio",
            post(generate_audio_handler).get(get_audio_handler),
        )
        .route("/v1/articles", get(list_summaries_handler))
        .route("/v1/articles/by-url", get(get_summary_by_url_handler))
        .route(
            "/v1/articles/{summary_id}",
            get(get_summary_handler)
                .patch(update_summary_handler)
                .delete(delete_summary_handler),
        )
        .route(
            "/v1/articles/{summary_id}/content",
            get(get_summary_content_handler),
        )
        .route(
            "/v1/articles/{summary_id}/favorite",
            post(toggle_favorite_handler),
        )
        .route("/v1/requests", post(submit_request_handler))
        .route("/v1/requests/{request_id}", get(get_request_handler))
        .route(
            "/v1/requests/{request_id}/status",
            get(get_request_status_handler),
        )
        .route(
            "/v1/requests/{request_id}/retry",
            post(retry_request_handler),
        )
        .route("/v1/proxy/image", get(proxy_image_handler))
        .route("/v1/notifications/device", post(register_device_handler))
}

pub(crate) fn implemented_route_map() -> BTreeMap<&'static str, BTreeSet<String>> {
    let mut routes = BTreeMap::new();
    for path in [SUMMARY_ROUTE_PATHS[0], ARTICLE_ROUTE_PATHS[0]] {
        routes.insert(path, set_of(["GET"]));
    }
    for path in [SUMMARY_ROUTE_PATHS[1], ARTICLE_ROUTE_PATHS[1]] {
        routes.insert(path, set_of(["GET"]));
    }
    for path in [SUMMARY_ROUTE_PATHS[2], ARTICLE_ROUTE_PATHS[2]] {
        routes.insert(path, set_of(["GET", "PATCH", "DELETE"]));
    }
    for path in [SUMMARY_ROUTE_PATHS[3], ARTICLE_ROUTE_PATHS[3]] {
        routes.insert(path, set_of(["GET"]));
    }
    for path in [SUMMARY_ROUTE_PATHS[4], ARTICLE_ROUTE_PATHS[4]] {
        routes.insert(path, set_of(["POST"]));
    }
    routes.insert(SUMMARY_ROUTE_PATHS[5], set_of(["GET", "POST"]));
    routes.insert("/v1/requests", set_of(["POST"]));
    routes.insert("/v1/requests/{request_id}", set_of(["GET"]));
    routes.insert("/v1/requests/{request_id}/status", set_of(["GET"]));
    routes.insert("/v1/requests/{request_id}/retry", set_of(["POST"]));
    routes.insert("/v1/proxy/image", set_of(["GET"]));
    routes.insert("/v1/notifications/device", set_of(["POST"]));
    routes
}

async fn list_summaries_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<SummaryListQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(query) => query.0,
        Err(response) => return response,
    };

    let limit = query.limit.unwrap_or(20);
    let offset = query.offset.unwrap_or(0);
    if !(1..=100).contains(&limit) || offset < 0 {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Invalid pagination parameters",
            None,
        );
    }
    if let Some(lang) = query.lang.as_deref() {
        if !matches!(lang, "en" | "ru" | "auto") {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "lang must be one of en, ru, auto",
                None,
            );
        }
    }
    let sort = query.sort.as_deref().unwrap_or("created_at_desc");
    if !matches!(sort, "created_at_desc" | "created_at_asc") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "sort must be created_at_desc or created_at_asc",
            None,
        );
    }

    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let filters = SummaryListFilters {
        user_id: user.user_id,
        limit,
        offset,
        is_read: query.is_read,
        is_favorited: query.is_favorited,
        lang: query.lang.as_deref(),
        start_date: query.start_date.as_deref(),
        end_date: query.end_date.as_deref(),
        sort,
    };
    let (summaries, total, unread_count) = match list_user_summaries(&connection, &filters) {
        Ok(values) => values,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };

    let items = summaries
        .into_iter()
        .map(summary_list_item_json)
        .collect::<Vec<_>>();
    let pagination = json!({
        "total": total,
        "limit": limit,
        "offset": offset,
        "hasMore": (offset + limit) < total,
    });
    let data = json!({
        "summaries": items,
        "pagination": pagination,
        "stats": {
            "totalSummaries": total,
            "unreadCount": unread_count,
        }
    });
    success_json_response_with_pagination(
        data,
        correlation_id.0,
        &state.runtime.config,
        Some(pagination),
    )
}

async fn get_summary_by_url_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    query: Result<Query<SummaryByUrlQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(query) => query.0,
        Err(response) => return response,
    };
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(summary_id) =
        (match get_summary_id_by_url_for_user(&connection, user.user_id, &query.url) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        })
    else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Article",
            &query.url,
        );
    };
    summary_detail_response(&state, correlation_id.0, user.user_id, summary_id)
}

async fn get_summary_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
) -> Response {
    summary_detail_response(&state, correlation_id.0, user.user_id, summary_id)
}

async fn get_summary_content_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
    query: Result<Query<SummaryContentQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(query) => query.0,
        Err(response) => return response,
    };
    let requested_format = query.format.unwrap_or_else(|| "markdown".to_string());
    if !matches!(requested_format.as_str(), "markdown" | "text") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "format must be markdown or text",
            None,
        );
    }

    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(summary) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Summary",
            &summary_id.to_string(),
        );
    };
    let Some(crawl_result) = (match get_crawl_result_by_request_api(&connection, summary.request_id)
    {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Content",
            &summary_id.to_string(),
        );
    };

    let metadata = crawl_result
        .metadata_json
        .clone()
        .unwrap_or_else(|| json!({}));
    let summary_metadata = summary
        .json_payload
        .as_ref()
        .and_then(|value| value.get("metadata"))
        .cloned()
        .unwrap_or_else(|| json!({}));
    let source_url = crawl_result
        .source_url
        .clone()
        .or(summary.request_input_url.clone())
        .or(summary.request_normalized_url.clone());
    let title = metadata
        .get("title")
        .and_then(Value::as_str)
        .or_else(|| summary_metadata.get("title").and_then(Value::as_str))
        .map(str::to_string);
    let domain = metadata
        .get("domain")
        .and_then(Value::as_str)
        .or_else(|| summary_metadata.get("domain").and_then(Value::as_str))
        .map(str::to_string);

    let (source_format, mut content) =
        if let Some(markdown) = crawl_result.content_markdown.as_deref() {
            ("markdown", markdown.to_string())
        } else if let Some(html) = crawl_result.content_html.as_deref() {
            ("html", html.to_string())
        } else if let Some(text) = summary.request_content_text.as_deref() {
            ("text", text.to_string())
        } else {
            return resource_not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                "Content",
                &summary_id.to_string(),
            );
        };

    let mut output_format = requested_format.clone();
    let mut content_type = match source_format {
        "markdown" => "text/markdown",
        "html" => "text/html",
        _ => "text/plain",
    };
    if requested_format == "text" {
        if source_format == "markdown" {
            content = clean_markdown_article_text(&content);
        } else if source_format == "html" {
            content = html_to_text(&content);
        }
        content_type = "text/plain";
    } else if source_format == "html" {
        content = html_to_text(&content);
        output_format = "text".to_string();
        content_type = "text/plain";
    } else if source_format != "markdown" {
        output_format = "text".to_string();
        content_type = "text/plain";
    }

    let checksum = sha256_hex(content.as_bytes());
    let size_bytes = content.as_bytes().len() as i64;
    let retrieved_at = normalize_datetime_text(crawl_result.updated_at.as_deref())
        .or_else(|| normalize_datetime_text(summary.created_at.as_deref()))
        .unwrap_or_else(iso_timestamp);

    success_json_response(
        json!({
            "content": {
                "summaryId": summary.id,
                "requestId": summary.request_id,
                "format": output_format,
                "content": content,
                "contentType": content_type,
                "lang": summary.lang,
                "sourceUrl": source_url,
                "title": title,
                "domain": domain,
                "retrievedAt": retrieved_at,
                "sizeBytes": size_bytes,
                "checksumSha256": checksum,
            }
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn update_summary_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
    payload: Result<Json<UpdateSummaryPayload>, JsonRejection>,
) -> Response {
    let payload = match parse_json(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(summary) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Summary",
            &summary_id.to_string(),
        );
    };

    if let Some(is_read) = payload.is_read {
        let result = if is_read {
            mark_summary_as_read(&connection, summary_id)
        } else {
            mark_summary_as_unread(&connection, summary_id)
        };
        if let Err(err) = result {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            );
        }
    }
    let updated = match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(Some(value)) => value,
        Ok(None) => summary,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    success_json_response(
        json!({
            "id": summary_id,
            "isRead": updated.is_read,
            "updatedAt": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn delete_summary_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(_) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Summary",
            &summary_id.to_string(),
        );
    };
    if let Err(err) = soft_delete_summary(&connection, summary_id) {
        return database_unavailable_response(
            &correlation_id.0,
            &state.runtime.config,
            &err.to_string(),
        );
    }
    success_json_response(
        json!({
            "id": summary_id,
            "deletedAt": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn toggle_favorite_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(_) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Summary",
            &summary_id.to_string(),
        );
    };
    let is_favorited = match toggle_summary_favorite(&connection, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    success_json_response(
        json!({
            "success": true,
            "isFavorited": is_favorited,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn submit_request_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    payload: Result<Json<SubmitRequestPayload>, JsonRejection>,
) -> Response {
    let payload = match parse_json(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let execution_config = ApiRequestExecutionConfig::from_env();

    match payload {
        SubmitRequestPayload::Url {
            input_url,
            lang_preference,
        } => {
            let normalized_url = match normalize_url_for_dedupe(&input_url) {
                Ok(value) => value,
                Err(message) => {
                    return validation_error_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        &message,
                        None,
                    );
                }
            };
            let dedupe_hash = compute_dedupe_hash(&normalized_url);
            if let Some(existing) = match get_request_by_dedupe_hash(&connection, &dedupe_hash) {
                Ok(value) => value,
                Err(err) => {
                    return database_unavailable_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        &err.to_string(),
                    )
                }
            } {
                if existing.user_id == Some(user.user_id) {
                    let summary_id = match get_summary_by_request_id(&connection, existing.id) {
                        Ok(value) => value.map(|summary| summary.id),
                        Err(err) => {
                            return database_unavailable_response(
                                &correlation_id.0,
                                &state.runtime.config,
                                &err.to_string(),
                            )
                        }
                    };
                    let summarized_at =
                        match get_request_by_id_for_user(&connection, user.user_id, existing.id) {
                            Ok(Some(value)) => normalize_datetime_text(value.created_at.as_deref()),
                            _ => None,
                        };
                    return success_json_response(
                        json!({
                            "isDuplicate": true,
                            "existingRequestId": existing.id,
                            "existingSummaryId": summary_id,
                            "message": "This URL was already summarized",
                            "summarizedAt": summarized_at,
                        }),
                        correlation_id.0,
                        &state.runtime.config,
                    );
                }
            }

            let request = match create_request(
                &connection,
                &CreateRequestInput {
                    request_type: "url".to_string(),
                    status: "pending".to_string(),
                    correlation_id: Some(build_api_correlation_id(user.user_id)),
                    chat_id: None,
                    user_id: Some(user.user_id),
                    input_url: Some(input_url.clone()),
                    normalized_url: Some(normalized_url),
                    dedupe_hash: Some(dedupe_hash),
                    input_message_id: None,
                    fwd_from_chat_id: None,
                    fwd_from_msg_id: None,
                    lang_detected: Some(normalize_language_preference(&lang_preference)),
                    content_text: None,
                    route_version: 1,
                },
            ) {
                Ok(value) => value,
                Err(err) => {
                    return database_unavailable_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        &err.to_string(),
                    )
                }
            };

            let api_request =
                match get_request_by_id_for_user(&connection, user.user_id, request.id) {
                    Ok(Some(value)) => value,
                    Ok(None) => request_record_fallback(request.clone()),
                    Err(err) => {
                        return database_unavailable_response(
                            &correlation_id.0,
                            &state.runtime.config,
                            &err.to_string(),
                        )
                    }
                };
            let state_for_job = state.clone();
            if execution_config.execute_inline {
                execute_url_job(state_for_job, api_request.clone()).await;
            } else {
                tokio::spawn(async move {
                    execute_url_job(state_for_job, api_request).await;
                });
            }

            success_json_response(
                json!({
                    "request": {
                        "requestId": request.id,
                        "correlationId": request.correlation_id,
                        "type": "url",
                        "status": "pending",
                        "estimatedWaitSeconds": 15,
                        "createdAt": iso_timestamp(),
                        "isDuplicate": false,
                    }
                }),
                correlation_id.0,
                &state.runtime.config,
            )
        }
        SubmitRequestPayload::Forward {
            content_text,
            forward_metadata,
            lang_preference,
        } => {
            let request = match create_request(
                &connection,
                &CreateRequestInput {
                    request_type: "forward".to_string(),
                    status: "pending".to_string(),
                    correlation_id: Some(build_api_correlation_id(user.user_id)),
                    chat_id: None,
                    user_id: Some(user.user_id),
                    input_url: None,
                    normalized_url: None,
                    dedupe_hash: None,
                    input_message_id: None,
                    fwd_from_chat_id: Some(forward_metadata.from_chat_id),
                    fwd_from_msg_id: Some(forward_metadata.from_message_id),
                    lang_detected: Some(normalize_language_preference(&lang_preference)),
                    content_text: Some(content_text),
                    route_version: 1,
                },
            ) {
                Ok(value) => value,
                Err(err) => {
                    return database_unavailable_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        &err.to_string(),
                    )
                }
            };
            let api_request =
                match get_request_by_id_for_user(&connection, user.user_id, request.id) {
                    Ok(Some(value)) => value,
                    Ok(None) => request_record_fallback(request.clone()),
                    Err(err) => {
                        return database_unavailable_response(
                            &correlation_id.0,
                            &state.runtime.config,
                            &err.to_string(),
                        )
                    }
                };
            let state_for_job = state.clone();
            let source_chat_title = forward_metadata.from_chat_title.clone();
            if execution_config.execute_inline {
                execute_forward_job(state_for_job, api_request.clone(), source_chat_title).await;
            } else {
                tokio::spawn(async move {
                    execute_forward_job(state_for_job, api_request, source_chat_title).await;
                });
            }

            success_json_response(
                json!({
                    "request": {
                        "requestId": request.id,
                        "correlationId": request.correlation_id,
                        "type": "forward",
                        "status": "pending",
                        "estimatedWaitSeconds": 10,
                        "createdAt": iso_timestamp(),
                        "isDuplicate": false,
                    }
                }),
                correlation_id.0,
                &state.runtime.config,
            )
        }
    }
}

async fn get_request_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(request_id): AxumPath<i64>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(request) = (match get_request_by_id_for_user(&connection, user.user_id, request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request",
            &request_id.to_string(),
        );
    };
    let crawl_result = match get_crawl_result_by_request_api(&connection, request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let llm_calls = match list_llm_calls_by_request(&connection, request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let summary = match get_summary_by_request_id(&connection, request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };

    success_json_response(
        json!({
            "request": {
                "id": request.id,
                "type": request.request_type,
                "status": api_visible_request_status(&request.status),
                "correlationId": request.correlation_id,
                "inputUrl": request.input_url,
                "normalizedUrl": request.normalized_url,
                "dedupeHash": request.dedupe_hash,
                "createdAt": normalize_datetime_text(request.created_at.as_deref()).unwrap_or_else(iso_timestamp),
                "langDetected": request.lang_detected,
            },
            "crawlResult": crawl_result.as_ref().map(|value| json!({
                "status": value.status,
                "httpStatus": value.http_status,
                "latencyMs": value.latency_ms,
                "error": value.error_text,
            })),
            "llmCalls": llm_calls.iter().map(|call| {
                json!({
                    "id": call.id,
                    "model": call.model,
                    "status": call.status,
                    "tokensPrompt": call.tokens_prompt,
                    "tokensCompletion": call.tokens_completion,
                    "costUsd": call.cost_usd,
                    "latencyMs": call.latency_ms,
                    "createdAt": normalize_datetime_text(call.created_at.as_deref())
                        .or_else(|| normalize_datetime_text(call.updated_at.as_deref()))
                        .unwrap_or_else(iso_timestamp),
                })
            }).collect::<Vec<_>>(),
            "summary": summary.as_ref().map(|value| json!({
                "id": value.id,
                "status": "success",
                "createdAt": normalize_datetime_text(value.created_at.as_deref()).unwrap_or_else(iso_timestamp),
            })),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_request_status_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(request_id): AxumPath<i64>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(request) = (match get_request_by_id_for_user(&connection, user.user_id, request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request",
            &request_id.to_string(),
        );
    };

    let internal_status = request.status.clone();
    let visible_status = api_visible_request_status(&internal_status);
    let mut stage = "pending".to_string();
    let mut progress = Value::Null;
    let mut estimated_seconds_remaining = Value::Null;
    let mut queue_position = Value::Null;
    let mut error_stage = Value::Null;
    let mut error_type = Value::Null;
    let mut error_message = Value::Null;
    let mut error_reason_code = Value::Null;
    let mut retryable = json!(false);
    let mut debug = Value::Null;
    let mut can_retry = false;

    if visible_status == "processing" {
        let crawl_result = match get_crawl_result_by_request_api(&connection, request_id) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        };
        let llm_calls = match list_llm_calls_by_request(&connection, request_id) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        };
        let summary = match get_summary_by_request_id(&connection, request_id) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        };

        if crawl_result.is_none() || internal_status == "extracting" {
            stage = "crawling".to_string();
            progress = json!({"current_step": 1, "total_steps": 3, "percentage": 33});
        } else if llm_calls.is_empty()
            || summary.is_none()
            || matches!(
                internal_status.as_str(),
                "summarizing" | "enriching" | "persisting"
            )
        {
            stage = "processing".to_string();
            progress = json!({"current_step": 2, "total_steps": 3, "percentage": 66});
        } else {
            stage = "processing".to_string();
            progress = json!({"current_step": 3, "total_steps": 3, "percentage": 90});
        }
        estimated_seconds_remaining = json!(8);
    } else if visible_status == "pending" {
        stage = "pending".to_string();
        if let Some(created_at) = request.created_at.as_deref() {
            let position = match count_pending_requests_before(&connection, created_at) {
                Ok(value) => value + 1,
                Err(err) => {
                    return database_unavailable_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        &err.to_string(),
                    )
                }
            };
            queue_position = json!(position);
        }
    } else if matches!(visible_status.as_str(), "ok" | "success") {
        stage = "complete".to_string();
    } else if visible_status == "error" {
        stage = "failed".to_string();
        let details = match derive_request_error_details(&connection, &request) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        };
        error_stage = optional_json(details.get("stage").cloned());
        error_type = optional_json(details.get("error_type").cloned());
        error_message = optional_json(
            details
                .get("message")
                .cloned()
                .or_else(|| Some(Value::String("Request failed".to_string()))),
        );
        error_reason_code = optional_json(details.get("reason_code").cloned());
        retryable = optional_json(details.get("retryable").cloned());
        debug = optional_json(details.get("debug").cloned());
        can_retry = true;
    } else if visible_status == "cancelled" {
        stage = "failed".to_string();
        error_message = json!("Request was cancelled");
        error_reason_code = json!("REQUEST_CANCELLED");
        retryable = json!(true);
        can_retry = true;
    }

    success_json_response(
        json!({
            "requestId": request_id,
            "status": visible_status,
            "stage": stage,
            "progress": progress,
            "estimatedSecondsRemaining": estimated_seconds_remaining,
            "queuePosition": queue_position,
            "errorStage": error_stage,
            "errorType": error_type,
            "errorMessage": error_message,
            "errorReasonCode": error_reason_code,
            "retryable": retryable,
            "debug": debug,
            "canRetry": can_retry,
            "correlationId": request.correlation_id,
            "updatedAt": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn retry_request_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(request_id): AxumPath<i64>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(original_request) =
        (match get_request_by_id_for_user(&connection, user.user_id, request_id) {
            Ok(value) => value,
            Err(err) => {
                return database_unavailable_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    &err.to_string(),
                )
            }
        })
    else {
        return resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "Request",
            &request_id.to_string(),
        );
    };
    if api_visible_request_status(&original_request.status) != "error" {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Only failed requests can be retried",
            None,
        );
    }

    let new_correlation_id = format!(
        "{}-retry-1",
        original_request
            .correlation_id
            .clone()
            .unwrap_or_else(|| build_api_correlation_id(user.user_id))
    );
    let new_request = match create_request(
        &connection,
        &CreateRequestInput {
            request_type: original_request.request_type.clone(),
            status: "pending".to_string(),
            correlation_id: Some(new_correlation_id.clone()),
            chat_id: original_request.chat_id,
            user_id: Some(user.user_id),
            input_url: original_request.input_url.clone(),
            normalized_url: original_request.normalized_url.clone(),
            dedupe_hash: original_request.dedupe_hash.clone(),
            input_message_id: original_request.input_message_id,
            fwd_from_chat_id: original_request.fwd_from_chat_id,
            fwd_from_msg_id: original_request.fwd_from_msg_id,
            lang_detected: original_request.lang_detected.clone(),
            content_text: original_request.content_text.clone(),
            route_version: original_request.route_version,
        },
    ) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let api_request = match get_request_by_id_for_user(&connection, user.user_id, new_request.id) {
        Ok(Some(value)) => value,
        Ok(None) => request_record_fallback(new_request.clone()),
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };

    let execution_config = ApiRequestExecutionConfig::from_env();
    let state_for_job = state.clone();
    if original_request.request_type == "forward" {
        if execution_config.execute_inline {
            execute_forward_job(state_for_job, api_request.clone(), None).await;
        } else {
            tokio::spawn(async move {
                execute_forward_job(state_for_job, api_request, None).await;
            });
        }
    } else if execution_config.execute_inline {
        execute_url_job(state_for_job, api_request.clone()).await;
    } else {
        tokio::spawn(async move {
            execute_url_job(state_for_job, api_request).await;
        });
    }

    success_json_response(
        json!({
            "newRequestId": new_request.id,
            "correlationId": new_correlation_id,
            "status": "pending",
            "createdAt": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn proxy_image_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    query: Result<Query<ProxyQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(query) => query.0,
        Err(response) => return response,
    };
    if !query.url.starts_with("http://") && !query.url.starts_with("https://") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Invalid URL scheme",
            None,
        );
    }

    let client = match Client::builder()
        .redirect(Policy::none())
        .timeout(std::time::Duration::from_secs(10))
        .build()
    {
        Ok(client) => client,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Internal proxy error",
                "INTERNAL_ERROR",
                Some(json!({"reason": err.to_string()})),
                false,
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };

    let mut current_url = query.url;
    let user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36";
    for _ in 0..=5 {
        if let Err(message) = ensure_public_proxy_url(&current_url).await {
            return error_json_response(
                StatusCode::FORBIDDEN,
                "FORBIDDEN",
                &message,
                "authorization",
                false,
                correlation_id.0,
                &state.runtime.config,
                None,
                None,
                Vec::new(),
            );
        }

        let response = match client
            .get(&current_url)
            .header("User-Agent", user_agent)
            .send()
            .await
        {
            Ok(response) => response,
            Err(err) => {
                return error_json_response(
                    StatusCode::BAD_GATEWAY,
                    "EXTERNAL_API_ERROR",
                    "Failed to fetch upstream image",
                    "external_service",
                    true,
                    correlation_id.0,
                    &state.runtime.config,
                    Some(json!({"reason": err.to_string()})),
                    None,
                    Vec::new(),
                );
            }
        };

        if response.status().is_redirection() {
            let Some(location) = response
                .headers()
                .get(LOCATION)
                .and_then(|value| value.to_str().ok())
            else {
                return error_json_response(
                    StatusCode::BAD_GATEWAY,
                    "EXTERNAL_API_ERROR",
                    "Upstream redirect missing location",
                    "external_service",
                    false,
                    correlation_id.0,
                    &state.runtime.config,
                    None,
                    None,
                    Vec::new(),
                );
            };
            let base = match Url::parse(&current_url) {
                Ok(value) => value,
                Err(_) => {
                    return validation_error_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        "Invalid redirect URL scheme",
                        None,
                    );
                }
            };
            let next_url = match base.join(location) {
                Ok(value) => value.to_string(),
                Err(_) => {
                    return validation_error_response(
                        &correlation_id.0,
                        &state.runtime.config,
                        "Invalid redirect URL scheme",
                        None,
                    );
                }
            };
            if !next_url.starts_with("http://") && !next_url.starts_with("https://") {
                return validation_error_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Invalid redirect URL scheme",
                    None,
                );
            }
            current_url = next_url;
            continue;
        }

        if response.status().as_u16() >= 400 {
            return error_json_response(
                StatusCode::NOT_FOUND,
                "NOT_FOUND",
                "Image not found or inaccessible",
                "not_found",
                false,
                correlation_id.0,
                &state.runtime.config,
                None,
                None,
                Vec::new(),
            );
        }

        let content_type = response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        if !content_type.starts_with("image/") {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "URL does not point to an image",
                None,
            );
        }
        if let Some(len) = response
            .headers()
            .get(CONTENT_LENGTH)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<usize>().ok())
        {
            if len > MAX_PROXY_RESPONSE_BYTES {
                return error_json_response(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "VALIDATION_ERROR",
                    "Image too large (max 10 MB)",
                    "validation",
                    false,
                    correlation_id.0,
                    &state.runtime.config,
                    None,
                    None,
                    Vec::new(),
                );
            }
        }

        let bytes = match response.bytes().await {
            Ok(value) => value,
            Err(err) => {
                return error_json_response(
                    StatusCode::BAD_GATEWAY,
                    "EXTERNAL_API_ERROR",
                    "Failed to fetch upstream image",
                    "external_service",
                    true,
                    correlation_id.0,
                    &state.runtime.config,
                    Some(json!({"reason": err.to_string()})),
                    None,
                    Vec::new(),
                );
            }
        };
        if bytes.len() > MAX_PROXY_RESPONSE_BYTES {
            return error_json_response(
                StatusCode::PAYLOAD_TOO_LARGE,
                "VALIDATION_ERROR",
                "Image too large (max 10 MB)",
                "validation",
                false,
                correlation_id.0,
                &state.runtime.config,
                None,
                None,
                Vec::new(),
            );
        }

        return (
            StatusCode::OK,
            [
                (
                    CONTENT_TYPE,
                    HeaderValue::from_str(&content_type)
                        .unwrap_or_else(|_| HeaderValue::from_static("image/jpeg")),
                ),
                (
                    CACHE_CONTROL,
                    HeaderValue::from_static("public, max-age=86400"),
                ),
            ],
            Body::from(bytes),
        )
            .into_response();
    }

    error_json_response(
        StatusCode::BAD_GATEWAY,
        "EXTERNAL_API_ERROR",
        "Too many redirects",
        "external_service",
        false,
        correlation_id.0,
        &state.runtime.config,
        None,
        None,
        Vec::new(),
    )
}

async fn register_device_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    payload: Result<Json<DeviceRegistrationPayload>, JsonRejection>,
) -> Response {
    let payload = match parse_json(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if payload.token.trim().is_empty() || payload.token.len() > 500 {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "token must be between 1 and 500 characters",
            None,
        );
    }
    if !matches!(payload.platform.as_str(), "ios" | "android") {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "platform must be ios or android",
            None,
        );
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    match upsert_user_device(
        &connection,
        user.user_id,
        payload.token.trim(),
        payload.platform.as_str(),
        payload.device_id.as_deref(),
    ) {
        Ok(_) => Json(json!({"status": "ok"})).into_response(),
        Err(bsr_persistence::PersistenceError::MissingRow(_)) => resource_not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "User",
            &user.user_id.to_string(),
        ),
        Err(err) => database_unavailable_response(
            &correlation_id.0,
            &state.runtime.config,
            &err.to_string(),
        ),
    }
}

async fn generate_audio_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
    query: Result<Query<TtsQuery>, QueryRejection>,
) -> Response {
    let query = match parse_query(query, &correlation_id.0, &state.runtime.config) {
        Ok(query) => query.0,
        Err(response) => return response,
    };
    let tts_config = TtsRuntimeConfig::from_env();
    if !tts_config.enabled {
        return error_json_response(
            StatusCode::NOT_IMPLEMENTED,
            "FEATURE_DISABLED",
            "TTS is not enabled",
            "internal",
            false,
            correlation_id.0,
            &state.runtime.config,
            None,
            None,
            Vec::new(),
        );
    }

    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(summary) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id.0,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return plain_not_found_response("Summary not found");
    };

    let requested_source = query
        .source_field
        .as_deref()
        .filter(|value| matches!(*value, "summary_250" | "summary_1000" | "tldr"))
        .unwrap_or("summary_1000");
    let Some(summary_payload) = summary.json_payload.as_ref() else {
        return success_json_response(
            json!({
                "summaryId": summary_id,
                "status": "error",
                "charCount": Value::Null,
                "fileSizeBytes": Value::Null,
                "latencyMs": Value::Null,
                "error": "No summary text available",
            }),
            correlation_id.0,
            &state.runtime.config,
        );
    };

    let (source_field, text) = match resolve_tts_text(summary_payload, requested_source) {
        Some(value) => value,
        None => {
            return success_json_response(
                json!({
                    "summaryId": summary_id,
                    "status": "error",
                    "charCount": Value::Null,
                    "fileSizeBytes": Value::Null,
                    "latencyMs": Value::Null,
                    "error": "No summary text available",
                }),
                correlation_id.0,
                &state.runtime.config,
            );
        }
    };

    if let Ok(Some(existing)) = get_audio_generation_by_summary(&connection, summary_id) {
        if existing.status == "completed"
            && existing.source_field == source_field
            && existing
                .file_path
                .as_deref()
                .is_some_and(|path| Path::new(path).is_file())
        {
            return success_json_response(
                json!({
                    "summaryId": summary_id,
                    "status": "completed",
                    "charCount": existing.char_count,
                    "fileSizeBytes": existing.file_size_bytes,
                    "latencyMs": existing.latency_ms,
                    "error": existing.error_text,
                }),
                correlation_id.0,
                &state.runtime.config,
            );
        }
    }

    if tts_config.api_key.is_none() {
        return success_json_response(
            json!({
                "summaryId": summary_id,
                "status": "error",
                "charCount": text.chars().count(),
                "fileSizeBytes": Value::Null,
                "latencyMs": Value::Null,
                "error": "Invalid API key",
            }),
            correlation_id.0,
            &state.runtime.config,
        );
    }

    let char_count = text.chars().count() as i64;
    if let Err(err) = start_audio_generation(
        &connection,
        summary_id,
        "elevenlabs",
        &tts_config.voice_id,
        &tts_config.model,
        source_field,
        summary.lang.as_deref(),
        char_count,
    ) {
        return database_unavailable_response(
            &correlation_id.0,
            &state.runtime.config,
            &err.to_string(),
        );
    }

    let started_at = Instant::now();
    let audio_bytes = match synthesize_audio(&tts_config, &text).await {
        Ok(bytes) => bytes,
        Err(message) => {
            let latency_ms = started_at.elapsed().as_millis() as i64;
            let _ = fail_audio_generation(&connection, summary_id, &message, latency_ms);
            return success_json_response(
                json!({
                    "summaryId": summary_id,
                    "status": "error",
                    "charCount": char_count,
                    "fileSizeBytes": Value::Null,
                    "latencyMs": latency_ms,
                    "error": message,
                }),
                correlation_id.0,
                &state.runtime.config,
            );
        }
    };
    let latency_ms = started_at.elapsed().as_millis() as i64;
    if let Err(err) = fs::create_dir_all(&tts_config.audio_storage_path).await {
        let _ = fail_audio_generation(&connection, summary_id, &err.to_string(), latency_ms);
        return success_json_response(
            json!({
                "summaryId": summary_id,
                "status": "error",
                "charCount": char_count,
                "fileSizeBytes": Value::Null,
                "latencyMs": latency_ms,
                "error": err.to_string(),
            }),
            correlation_id.0,
            &state.runtime.config,
        );
    }
    let file_path = tts_config
        .audio_storage_path
        .join(format!("{summary_id}.mp3"));
    if let Err(err) = fs::write(&file_path, &audio_bytes).await {
        let _ = fail_audio_generation(&connection, summary_id, &err.to_string(), latency_ms);
        return success_json_response(
            json!({
                "summaryId": summary_id,
                "status": "error",
                "charCount": char_count,
                "fileSizeBytes": Value::Null,
                "latencyMs": latency_ms,
                "error": err.to_string(),
            }),
            correlation_id.0,
            &state.runtime.config,
        );
    }
    let file_size_bytes = audio_bytes.len() as i64;
    if let Err(err) = complete_audio_generation(
        &connection,
        summary_id,
        &file_path.to_string_lossy(),
        file_size_bytes,
        latency_ms,
    ) {
        return database_unavailable_response(
            &correlation_id.0,
            &state.runtime.config,
            &err.to_string(),
        );
    }

    success_json_response(
        json!({
            "summaryId": summary_id,
            "status": "completed",
            "charCount": char_count,
            "fileSizeBytes": file_size_bytes,
            "latencyMs": latency_ms,
            "error": Value::Null,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_audio_handler(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    AxumPath(summary_id): AxumPath<i64>,
) -> Response {
    let tts_config = TtsRuntimeConfig::from_env();
    if !tts_config.enabled {
        return plain_error_response(StatusCode::NOT_IMPLEMENTED, "TTS is not enabled");
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(_) => {
            return plain_error_response(
                StatusCode::SERVICE_UNAVAILABLE,
                "Database temporarily unavailable",
            )
        }
    };
    let Some(_) = (match get_summary_by_id_for_user(&connection, user.user_id, summary_id) {
        Ok(value) => value,
        Err(_) => {
            return plain_error_response(
                StatusCode::SERVICE_UNAVAILABLE,
                "Database temporarily unavailable",
            )
        }
    }) else {
        return plain_not_found_response("Summary not found");
    };
    let Some(audio) = (match get_audio_generation_by_summary(&connection, summary_id) {
        Ok(value) => value,
        Err(_) => {
            return plain_error_response(
                StatusCode::SERVICE_UNAVAILABLE,
                "Database temporarily unavailable",
            )
        }
    }) else {
        return plain_not_found_response("Audio not generated yet");
    };
    if audio.status != "completed" || audio.file_path.as_deref().is_none() {
        return plain_not_found_response("Audio not generated yet");
    }
    let path = PathBuf::from(audio.file_path.unwrap_or_default());
    let bytes = match fs::read(&path).await {
        Ok(bytes) => bytes,
        Err(err) if err.kind() == ErrorKind::NotFound => {
            return plain_not_found_response("Audio file missing");
        }
        Err(_) => {
            return plain_error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                "Failed to read audio file",
            )
        }
    };

    (
        StatusCode::OK,
        [
            (CONTENT_TYPE, HeaderValue::from_static("audio/mpeg")),
            (
                CONTENT_DISPOSITION,
                HeaderValue::from_str(&format!(
                    "attachment; filename=\"summary-{summary_id}.mp3\""
                ))
                .unwrap_or_else(|_| HeaderValue::from_static("attachment")),
            ),
        ],
        Body::from(bytes),
    )
        .into_response()
}

fn summary_detail_response(
    state: &AppState,
    correlation_id: String,
    user_id: i64,
    summary_id: i64,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let Some(summary) = (match get_summary_by_id_for_user(&connection, user_id, summary_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    }) else {
        return resource_not_found_response(
            &correlation_id,
            &state.runtime.config,
            "Summary",
            &summary_id.to_string(),
        );
    };
    let crawl_result = match get_crawl_result_by_request_api(&connection, summary.request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let llm_calls = match list_llm_calls_by_request(&connection, summary.request_id) {
        Ok(value) => value,
        Err(err) => {
            return database_unavailable_response(
                &correlation_id,
                &state.runtime.config,
                &err.to_string(),
            )
        }
    };
    let json_payload = summary.json_payload.clone().unwrap_or_else(|| json!({}));
    let metadata = crawl_result
        .as_ref()
        .and_then(|value| value.metadata_json.clone())
        .unwrap_or_else(|| json!({}));
    let entities = json_payload
        .get("entities")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let readability = json_payload
        .get("readability")
        .and_then(Value::as_object)
        .cloned();
    let latest_llm = llm_calls.last();
    let total_llm_latency: i64 = llm_calls
        .iter()
        .map(|call| call.latency_ms.unwrap_or(0))
        .sum();

    success_json_response(
        json!({
            "summary": {
                "summary250": get_json_string(&json_payload, "summary_250"),
                "summary1000": get_json_string(&json_payload, "summary_1000"),
                "tldr": get_json_string(&json_payload, "tldr"),
                "keyIdeas": get_json_array_strings(&json_payload, "key_ideas"),
                "topicTags": get_json_array_strings(&json_payload, "topic_tags"),
                "entities": {
                    "people": entities.get("people").cloned().unwrap_or_else(|| json!([])),
                    "organizations": entities
                        .get("organizations")
                        .cloned()
                        .unwrap_or_else(|| json!([])),
                    "locations": entities.get("locations").cloned().unwrap_or_else(|| json!([])),
                },
                "estimatedReadingTimeMin": get_json_i64(&json_payload, "estimated_reading_time_min"),
                "keyStats": normalize_key_stats(&json_payload),
                "answeredQuestions": json_payload
                    .get("answered_questions")
                    .cloned()
                    .unwrap_or_else(|| json!([])),
                "readability": readability.map(|value| json!({
                    "method": value.get("method"),
                    "score": value.get("score").and_then(Value::as_f64).unwrap_or(0.0),
                    "level": value.get("level"),
                })),
                "seoKeywords": json_payload.get("seo_keywords").cloned().unwrap_or_else(|| json!([])),
            },
            "request": {
                "id": summary.request_id.to_string(),
                "type": summary.request_type,
                "url": summary.request_input_url,
                "normalizedUrl": summary.request_normalized_url,
                "dedupeHash": summary.request_dedupe_hash,
                "status": summary.request_status.as_ref().map(|value| api_visible_request_status(value)),
                "langDetected": summary.request_lang_detected,
                "createdAt": normalize_datetime_text(summary.request_created_at.as_deref())
                    .unwrap_or_else(iso_timestamp),
                "updatedAt": normalize_datetime_text(summary.request_updated_at.as_deref())
                    .or_else(|| normalize_datetime_text(summary.request_created_at.as_deref()))
                    .unwrap_or_else(iso_timestamp),
            },
            "source": {
                "url": crawl_result.as_ref().and_then(|value| value.source_url.clone()),
                "title": metadata.get("title").cloned(),
                "domain": metadata.get("domain").cloned(),
                "author": metadata.get("author").cloned(),
                "publishedAt": metadata.get("published_at").cloned(),
                "wordCount": json_payload.get("word_count").cloned(),
                "contentType": metadata
                    .get("content_type")
                    .cloned()
                    .or_else(|| metadata.get("og:type").cloned())
                    .or_else(|| metadata.get("type").cloned()),
            },
            "processing": {
                "modelUsed": latest_llm.and_then(|value| value.model.clone()),
                "tokensUsed": latest_llm.map(|value| value.tokens_prompt.unwrap_or(0) + value.tokens_completion.unwrap_or(0)),
                "processingTimeMs": if total_llm_latency > 0 { Some(total_llm_latency) } else { None::<i64> },
                "crawlTimeMs": crawl_result.as_ref().and_then(|value| value.latency_ms),
                "confidence": json_payload.get("confidence").and_then(Value::as_f64),
                "hallucinationRisk": normalize_hallucination_risk(
                    json_payload
                        .get("hallucination_risk")
                        .and_then(Value::as_str)
                        .unwrap_or("unknown"),
                ),
            }
        }),
        correlation_id,
        &state.runtime.config,
    )
}

async fn execute_url_job(state: AppState, request: ApiRequestRecord) {
    let input_url = request.input_url.clone().unwrap_or_default();
    let execution_config = ApiRequestExecutionConfig::from_env();
    let input = UrlExecuteInput {
        existing_request_id: Some(request.id),
        correlation_id: request.correlation_id.clone(),
        db_path: Some(state.runtime.config.db_path.display().to_string()),
        input_url,
        chat_id: request.chat_id,
        user_id: request.user_id,
        input_message_id: request.input_message_id,
        silent: true,
        preferred_language: request
            .lang_detected
            .clone()
            .unwrap_or_else(default_language),
        route_version: request.route_version,
        prompt_version: execution_config.prompt_version,
        enable_chunking: execution_config.enable_chunking,
        configured_chunk_max_chars: execution_config.chunk_max_chars,
        primary_model: execution_config.primary_model,
        long_context_model: execution_config.long_context_model,
        fallback_models: execution_config.fallback_models,
        flash_model: execution_config.flash_model,
        flash_fallback_models: execution_config.flash_fallback_models,
        structured_output_mode: execution_config.structured_output_mode,
        temperature: execution_config.temperature,
        top_p: execution_config.top_p,
        json_temperature: execution_config.json_temperature,
        json_top_p: execution_config.json_top_p,
        vision_model: None,
        enable_two_pass_enrichment: execution_config.enable_two_pass_enrichment,
        web_search_context: None,
        persist_is_read: Some(false),
    };
    let mut emit = |_event: OrchestratorEvent| Ok(());
    if let Err(err) = execute_url_flow(&input, &mut emit).await {
        persist_background_failure(&state, request.id, &err.to_string());
    }
}

async fn execute_forward_job(
    state: AppState,
    request: ApiRequestRecord,
    source_chat_title: Option<String>,
) {
    let execution_config = ApiRequestExecutionConfig::from_env();
    let input = ForwardExecuteInput {
        existing_request_id: Some(request.id),
        correlation_id: request.correlation_id.clone(),
        db_path: Some(state.runtime.config.db_path.display().to_string()),
        text: request.content_text.clone().unwrap_or_default(),
        chat_id: request.chat_id,
        user_id: request.user_id,
        input_message_id: request.input_message_id,
        fwd_from_chat_id: request.fwd_from_chat_id,
        fwd_from_msg_id: request.fwd_from_msg_id,
        source_chat_title,
        source_user_first_name: None,
        source_user_last_name: None,
        forward_sender_name: None,
        preferred_language: request
            .lang_detected
            .clone()
            .unwrap_or_else(default_language),
        route_version: request.route_version,
        primary_model: execution_config.primary_model,
        fallback_models: execution_config.fallback_models,
        flash_model: execution_config.flash_model,
        flash_fallback_models: execution_config.flash_fallback_models,
        structured_output_mode: execution_config.structured_output_mode,
        temperature: execution_config.temperature,
        top_p: execution_config.top_p,
        json_temperature: execution_config.json_temperature,
        json_top_p: execution_config.json_top_p,
        enable_two_pass_enrichment: execution_config.enable_two_pass_enrichment,
        normalize_forward_prompt: true,
        prompt_version: execution_config.prompt_version,
        persist_is_read: Some(false),
    };
    let mut emit = |_event: OrchestratorEvent| Ok(());
    if let Err(err) = execute_forward_flow(&input, &mut emit).await {
        persist_background_failure(&state, request.id, &err.to_string());
    }
}

fn persist_background_failure(state: &AppState, request_id: i64, error_text: &str) {
    if let Ok(connection) = open_connection(&state.runtime.config.db_path) {
        let _ = update_request_error(
            &connection,
            request_id,
            &RequestErrorUpdate {
                status: "error".to_string(),
                error_type: Some("PROCESSING_ERROR".to_string()),
                error_message: Some(error_text.to_string()),
                processing_time_ms: None,
                error_context_json: Some(json!({
                    "stage": "background_execution",
                    "reason_code": "PROCESSING_ERROR",
                    "error_message": error_text,
                    "retryable": true,
                })),
            },
        );
    }
}

fn derive_request_error_details(
    connection: &rusqlite::Connection,
    request: &ApiRequestRecord,
) -> Result<HashMap<String, Value>, bsr_persistence::PersistenceError> {
    let mut details = HashMap::new();
    if let Some(request_ctx) = request
        .error_context_json
        .as_ref()
        .and_then(Value::as_object)
    {
        if let Some(value) = request_ctx.get("stage") {
            details.insert("stage".to_string(), value.clone());
        }
        if let Some(value) = request_ctx
            .get("error_type")
            .or_else(|| request_ctx.get("reason_code"))
        {
            details.insert("error_type".to_string(), value.clone());
        }
        if let Some(value) = request_ctx.get("error_message") {
            details.insert("message".to_string(), value.clone());
        }
        if let Some(value) = request_ctx.get("reason_code") {
            details.insert("reason_code".to_string(), value.clone());
        }
        details.insert(
            "retryable".to_string(),
            json!(request_ctx
                .get("retryable")
                .and_then(Value::as_bool)
                .unwrap_or(true)),
        );
        details.insert(
            "debug".to_string(),
            json!({
                "pipeline": request_ctx.get("pipeline"),
                "component": request_ctx.get("component"),
                "attempt": request_ctx.get("attempt"),
                "max_attempts": request_ctx.get("max_attempts"),
                "timestamp": request_ctx.get("timestamp"),
            }),
        );
        return Ok(details);
    }

    if let Some(call) = get_latest_llm_call_by_request(connection, request.id)? {
        if call.status.as_deref() == Some("error") || call.error_text.is_some() {
            let ctx = call.error_context_json.as_ref().and_then(Value::as_object);
            details.insert("stage".to_string(), json!("llm_summarization"));
            details.insert(
                "error_type".to_string(),
                ctx.and_then(|value| value.get("status_code").cloned())
                    .unwrap_or_else(|| json!("LLM_FAILED")),
            );
            details.insert(
                "message".to_string(),
                call.error_text
                    .map(Value::String)
                    .or_else(|| ctx.and_then(|value| value.get("message").cloned()))
                    .unwrap_or_else(|| json!("LLM summarization failed")),
            );
            details.insert("reason_code".to_string(), json!("LLM_FAILED"));
            details.insert("retryable".to_string(), json!(true));
            return Ok(details);
        }
    }

    if let Some(crawl) = get_crawl_result_by_request_api(connection, request.id)? {
        if crawl.status.as_deref() == Some("error") || crawl.error_text.is_some() {
            details.insert("stage".to_string(), json!("content_extraction"));
            details.insert(
                "error_type".to_string(),
                crawl
                    .firecrawl_error_code
                    .map(Value::String)
                    .unwrap_or_else(|| json!("EXTRACTION_FAILED")),
            );
            details.insert(
                "message".to_string(),
                crawl
                    .error_text
                    .map(Value::String)
                    .or_else(|| crawl.firecrawl_error_message.map(Value::String))
                    .unwrap_or_else(|| json!("Content extraction failed")),
            );
            details.insert("reason_code".to_string(), json!("EXTRACTION_FAILED"));
            details.insert("retryable".to_string(), json!(true));
        }
    }

    Ok(details)
}

fn request_record_fallback(request: bsr_persistence::RequestRecord) -> ApiRequestRecord {
    ApiRequestRecord {
        id: request.id,
        request_type: request.request_type,
        status: request.status,
        correlation_id: request.correlation_id,
        user_id: request.user_id,
        chat_id: request.chat_id,
        input_url: request.input_url,
        normalized_url: request.normalized_url,
        dedupe_hash: request.dedupe_hash,
        input_message_id: request.input_message_id,
        fwd_from_chat_id: request.fwd_from_chat_id,
        fwd_from_msg_id: request.fwd_from_msg_id,
        lang_detected: request.lang_detected,
        content_text: request.content_text,
        route_version: request.route_version,
        error_type: request.error_type,
        error_message: request.error_message,
        processing_time_ms: request.processing_time_ms,
        error_context_json: request.error_context_json,
        created_at: None,
        updated_at: None,
    }
}

fn summary_list_item_json(summary: ApiSummaryRecord) -> Value {
    let payload = summary.json_payload.unwrap_or_else(|| json!({}));
    let metadata = payload
        .get("metadata")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    json!({
        "id": summary.id,
        "requestId": summary.request_id,
        "title": metadata.get("title").cloned().unwrap_or_else(|| json!("Untitled")),
        "domain": metadata.get("domain").cloned().unwrap_or_else(|| json!("")),
        "url": summary.request_input_url.or(summary.request_normalized_url).unwrap_or_default(),
        "tldr": get_json_string(&payload, "tldr"),
        "summary250": get_json_string(&payload, "summary_250"),
        "readingTimeMin": get_json_i64(&payload, "estimated_reading_time_min"),
        "topicTags": payload.get("topic_tags").cloned().unwrap_or_else(|| json!([])),
        "isRead": summary.is_read,
        "isFavorited": summary.is_favorited,
        "lang": summary.lang.unwrap_or_else(default_language),
        "createdAt": normalize_datetime_text(summary.created_at.as_deref()).unwrap_or_else(iso_timestamp),
        "confidence": payload.get("confidence").and_then(Value::as_f64).unwrap_or(0.0),
        "hallucinationRisk": normalize_hallucination_risk(
            payload.get("hallucination_risk").and_then(Value::as_str).unwrap_or("unknown"),
        ),
        "imageUrl": metadata
            .get("image")
            .cloned()
            .or_else(|| metadata.get("og:image").cloned())
            .or_else(|| metadata.get("ogImage").cloned()),
    })
}

fn parse_json<T: DeserializeOwned>(
    payload: Result<Json<T>, JsonRejection>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<Json<T>, Response> {
    payload.map_err(|err| {
        validation_error_response(
            correlation_id,
            config,
            "Invalid request payload",
            Some(json!({"reason": err.body_text()})),
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
            "Invalid query parameters",
            Some(json!({"reason": err.body_text()})),
        )
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

fn database_unavailable_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    reason: &str,
) -> Response {
    internal_error_response(
        correlation_id,
        config,
        "Database temporarily unavailable",
        "DATABASE_ERROR",
        Some(json!({"reason": reason})),
        true,
        StatusCode::SERVICE_UNAVAILABLE,
    )
}

fn internal_error_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
    code: &str,
    details: Option<Value>,
    retryable: bool,
    status: StatusCode,
) -> Response {
    error_json_response(
        status,
        code,
        message,
        "internal",
        retryable,
        correlation_id.to_string(),
        config,
        details,
        None,
        Vec::new(),
    )
}

fn plain_not_found_response(message: &str) -> Response {
    (StatusCode::NOT_FOUND, message.to_string()).into_response()
}

fn plain_error_response(status: StatusCode, message: &str) -> Response {
    (status, message.to_string()).into_response()
}

fn set_of<const N: usize>(methods: [&str; N]) -> BTreeSet<String> {
    methods.into_iter().map(str::to_string).collect()
}

fn get_json_string(payload: &Value, key: &str) -> String {
    payload
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string()
}

fn get_json_i64(payload: &Value, key: &str) -> i64 {
    payload.get(key).and_then(Value::as_i64).unwrap_or_default()
}

fn get_json_array_strings(payload: &Value, key: &str) -> Value {
    payload
        .get(key)
        .and_then(Value::as_array)
        .map(|values| {
            Value::Array(
                values
                    .iter()
                    .filter_map(|value| value.as_str().map(|text| Value::String(text.to_string())))
                    .collect(),
            )
        })
        .unwrap_or_else(|| json!([]))
}

fn normalize_key_stats(payload: &Value) -> Value {
    payload
        .get("key_stats")
        .and_then(Value::as_array)
        .map(|values| {
            Value::Array(
                values
                    .iter()
                    .filter_map(Value::as_object)
                    .map(|value| {
                        json!({
                            "label": value.get("label").and_then(Value::as_str).unwrap_or_default(),
                            "value": value.get("value").and_then(Value::as_f64).unwrap_or_default(),
                            "unit": value.get("unit").and_then(Value::as_str).unwrap_or_default(),
                            "sourceExcerpt": value
                                .get("source_excerpt")
                                .or_else(|| value.get("sourceExcerpt"))
                                .and_then(Value::as_str)
                                .unwrap_or_default(),
                        })
                    })
                    .collect(),
            )
        })
        .unwrap_or_else(|| json!([]))
}

fn optional_json(value: Option<Value>) -> Value {
    value.unwrap_or(Value::Null)
}

fn normalize_hallucination_risk(raw: &str) -> &'static str {
    match raw {
        "low" => "low",
        "med" | "medium" => "medium",
        "high" => "high",
        _ => "unknown",
    }
}

fn api_visible_request_status(status: &str) -> String {
    match status {
        "extracting" | "summarizing" | "enriching" | "persisting" => "processing".to_string(),
        other => other.to_string(),
    }
}

fn build_api_correlation_id(user_id: i64) -> String {
    format!("api-{user_id}-{}", Utc::now().timestamp())
}

fn default_language() -> String {
    "auto".to_string()
}

fn normalize_language_preference(value: &str) -> String {
    match value.trim().to_lowercase().as_str() {
        "en" => "en".to_string(),
        "ru" => "ru".to_string(),
        _ => "auto".to_string(),
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn iso_timestamp() -> String {
    Utc::now().to_rfc3339().replace("+00:00", "Z")
}

fn clean_markdown_article_text(markdown: &str) -> String {
    let mut output = Vec::new();
    let mut previous_blank = false;
    for line in markdown.lines() {
        let trimmed = line.trim_end();
        if trimmed.is_empty() {
            if !previous_blank {
                output.push(String::new());
            }
            previous_blank = true;
            continue;
        }
        output.push(trimmed.to_string());
        previous_blank = false;
    }
    output.join("\n").trim().to_string()
}

fn html_to_text(html: &str) -> String {
    let mut output = String::with_capacity(html.len());
    let mut inside_tag = false;
    for ch in html.chars() {
        match ch {
            '<' => inside_tag = true,
            '>' => {
                inside_tag = false;
                output.push(' ');
            }
            _ if !inside_tag => output.push(ch),
            _ => {}
        }
    }
    output
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn normalize_url_for_dedupe(input: &str) -> Result<String, String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return Err("URL cannot be empty".to_string());
    }
    let mut url = Url::parse(trimmed).map_err(|err| format!("URL normalization failed: {err}"))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err(format!(
            "Unsupported URL scheme: {}. Only http and https are allowed.",
            url.scheme()
        ));
    }
    let Some(host) = url.host_str().map(str::to_lowercase) else {
        return Err("Invalid URL: missing hostname".to_string());
    };
    if host == "localhost" || host == "localhost.localdomain" {
        return Err("Localhost access not allowed".to_string());
    }
    let normalized_path = {
        let path = url.path();
        let decoded = percent_encoding::percent_decode_str(path)
            .decode_utf8()
            .map_err(|err| format!("URL normalization failed: {err}"))?;
        let encoded = percent_encoding::utf8_percent_encode(
            decoded.as_ref(),
            percent_encoding::NON_ALPHANUMERIC,
        )
        .to_string()
        .replace("%2F", "/")
        .replace("%40", "@")
        .replace("%3A", ":");
        if encoded.ends_with('/') && encoded != "/" {
            encoded.trim_end_matches('/').to_string()
        } else if encoded.is_empty() {
            "/".to_string()
        } else {
            encoded
        }
    };
    let mut query_pairs = form_urlencoded::parse(url.query().unwrap_or_default().as_bytes())
        .into_owned()
        .filter(|(key, _)| !TRACKING_PARAMS.contains(&key.to_lowercase().as_str()))
        .collect::<Vec<_>>();
    query_pairs.sort();
    let query = if query_pairs.is_empty() {
        None
    } else {
        Some(
            form_urlencoded::Serializer::new(String::new())
                .extend_pairs(query_pairs)
                .finish(),
        )
    };
    url.set_fragment(None);
    url.set_host(Some(&host))
        .map_err(|err| format!("URL normalization failed: {err}"))?;
    url.set_path(&normalized_path);
    url.set_query(query.as_deref());
    let normalized = url.to_string();
    Ok(canonicalize_twitter_url(&normalized).unwrap_or(normalized))
}

fn compute_dedupe_hash(normalized_url: &str) -> String {
    sha256_hex(normalized_url.as_bytes())
}

fn canonicalize_twitter_url(url: &str) -> Option<String> {
    let parsed = Url::parse(url).ok()?;
    let host = parsed.host_str()?.to_lowercase();
    let hosts = [
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
    ];
    if !hosts.contains(&host.as_str()) {
        return None;
    }
    let path = parsed.path().trim_end_matches('/');
    let segments = path
        .split('/')
        .filter(|segment| !segment.is_empty())
        .collect::<Vec<_>>();
    if segments.len() >= 3
        && segments[1] == "status"
        && segments[2].chars().all(|ch| ch.is_ascii_digit())
    {
        return Some(format!("https://x.com/i/web/status/{}", segments[2]));
    }
    if segments.len() >= 4
        && segments[0] == "i"
        && segments[1] == "web"
        && segments[2] == "status"
        && segments[3].chars().all(|ch| ch.is_ascii_digit())
    {
        return Some(format!("https://x.com/i/web/status/{}", segments[3]));
    }
    if segments.len() >= 3
        && segments[0] == "i"
        && segments[1] == "article"
        && segments[2].chars().all(|ch| ch.is_ascii_digit())
    {
        return Some(format!("https://x.com/i/article/{}", segments[2]));
    }
    None
}

async fn ensure_public_proxy_url(url: &str) -> Result<(), String> {
    let parsed = Url::parse(url).map_err(|_| "URL resolves to blocked address".to_string())?;
    let hostname = parsed
        .host_str()
        .ok_or_else(|| "URL resolves to blocked address".to_string())?;
    if matches!(
        hostname.to_lowercase().as_str(),
        "localhost" | "localhost.localdomain"
    ) {
        return Err("URL resolves to blocked address".to_string());
    }
    let port = parsed.port_or_known_default().unwrap_or(80);
    let resolved = tokio::net::lookup_host((hostname, port))
        .await
        .map_err(|_| "URL resolves to blocked address".to_string())?
        .collect::<Vec<SocketAddr>>();
    if resolved.is_empty() {
        return Err("URL resolves to blocked address".to_string());
    }
    for addr in resolved {
        if is_blocked_ip(addr.ip()) {
            return Err("URL resolves to blocked address".to_string());
        }
    }
    Ok(())
}

fn is_blocked_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(addr) => {
            addr.is_private()
                || addr.is_loopback()
                || addr.is_link_local()
                || addr.is_multicast()
                || addr.is_broadcast()
                || addr.is_unspecified()
                || ipv4_in_cidr(addr, Ipv4Addr::new(100, 64, 0, 0), 10)
                || ipv4_in_cidr(addr, Ipv4Addr::new(192, 0, 0, 0), 24)
                || ipv4_in_cidr(addr, Ipv4Addr::new(192, 0, 2, 0), 24)
                || ipv4_in_cidr(addr, Ipv4Addr::new(198, 51, 100, 0), 24)
                || ipv4_in_cidr(addr, Ipv4Addr::new(203, 0, 113, 0), 24)
                || ipv4_in_cidr(addr, Ipv4Addr::new(224, 0, 0, 0), 4)
                || ipv4_in_cidr(addr, Ipv4Addr::new(240, 0, 0, 0), 4)
        }
        IpAddr::V6(addr) => {
            addr.is_loopback()
                || addr.is_multicast()
                || addr.is_unspecified()
                || addr.is_unique_local()
                || addr.is_unicast_link_local()
        }
    }
}

fn ipv4_in_cidr(ip: Ipv4Addr, base: Ipv4Addr, prefix: u8) -> bool {
    let ip_value = u32::from(ip);
    let base_value = u32::from(base);
    let mask = if prefix == 0 {
        0
    } else {
        u32::MAX << (32 - prefix)
    };
    (ip_value & mask) == (base_value & mask)
}

fn resolve_tts_text<'a>(
    payload: &'a Value,
    requested_source: &'a str,
) -> Option<(&'a str, String)> {
    let requested = payload
        .get(requested_source)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|value| (requested_source, value.to_string()));
    if requested.is_some() {
        return requested;
    }
    for field in ["summary_1000", "summary_250", "tldr"] {
        if let Some(text) = payload
            .get(field)
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            return Some((field, text.to_string()));
        }
    }
    None
}

async fn synthesize_audio(config: &TtsRuntimeConfig, text: &str) -> Result<Vec<u8>, String> {
    let chunks = chunk_tts_text(text, config.max_chars_per_request);
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs_f64(config.timeout_sec))
        .build()
        .map_err(|err| err.to_string())?;
    let mut output = Vec::new();
    for chunk in chunks {
        let bytes = synthesize_chunk(&client, config, &chunk).await?;
        output.extend_from_slice(&bytes);
    }
    Ok(output)
}

async fn synthesize_chunk(
    client: &Client,
    config: &TtsRuntimeConfig,
    text: &str,
) -> Result<Vec<u8>, String> {
    let url = format!(
        "{}/text-to-speech/{}",
        config.base_url.trim_end_matches('/'),
        config.voice_id
    );
    let payload = json!({
        "text": text,
        "model_id": config.model,
        "voice_settings": {
            "stability": config.stability,
            "similarity_boost": config.similarity_boost,
            "speed": config.speed,
        },
        "output_format": config.output_format,
    });

    for attempt in 0..=2 {
        match client
            .post(&url)
            .header("xi-api-key", config.api_key.clone().unwrap_or_default())
            .header(CONTENT_TYPE, "application/json")
            .json(&payload)
            .send()
            .await
        {
            Ok(response) if response.status().is_success() => {
                return response
                    .bytes()
                    .await
                    .map(|value| value.to_vec())
                    .map_err(|err| err.to_string());
            }
            Ok(response) => {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                let retryable = matches!(status, 429 | 500 | 502 | 503 | 504);
                let message = if status == 401 {
                    "Invalid API key".to_string()
                } else if body.to_lowercase().contains("quota")
                    || body.to_lowercase().contains("characters")
                {
                    format!("Quota exceeded: {body}")
                } else {
                    format!(
                        "ElevenLabs API error ({status}): {}",
                        truncate_string(&body, 200)
                    )
                };
                if retryable && attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_secs(2_u64.pow(attempt + 1)))
                        .await;
                    continue;
                }
                return Err(message);
            }
            Err(err) => {
                if attempt < 2 {
                    tokio::time::sleep(std::time::Duration::from_secs(2_u64.pow(attempt + 1)))
                        .await;
                    continue;
                }
                return Err(format!("ElevenLabs request failed after 3 attempts: {err}"));
            }
        }
    }
    Err("ElevenLabs request failed".to_string())
}

fn chunk_tts_text(text: &str, max_chars: usize) -> Vec<String> {
    if text.chars().count() <= max_chars {
        return vec![text.to_string()];
    }
    let mut chunks = Vec::new();
    let mut current = String::new();
    for sentence in split_sentences(text) {
        let projected = if current.is_empty() {
            sentence.len()
        } else {
            current.len() + 1 + sentence.len()
        };
        if projected > max_chars && !current.is_empty() {
            chunks.push(current.trim().to_string());
            current.clear();
        }
        if !current.is_empty() {
            current.push(' ');
        }
        current.push_str(sentence);
    }
    if !current.trim().is_empty() {
        chunks.push(current.trim().to_string());
    }
    if chunks.is_empty() {
        vec![text.to_string()]
    } else {
        chunks
    }
}

fn split_sentences(text: &str) -> Vec<&str> {
    let mut sentences = Vec::new();
    let mut start = 0;
    for (index, ch) in text.char_indices() {
        if matches!(ch, '.' | '!' | '?') {
            let end = index + ch.len_utf8();
            let candidate = text[start..end].trim();
            if !candidate.is_empty() {
                sentences.push(candidate);
            }
            start = end;
        }
    }
    let remainder = text[start..].trim();
    if !remainder.is_empty() {
        sentences.push(remainder);
    }
    sentences
}

fn truncate_string(text: &str, max_len: usize) -> String {
    if text.len() <= max_len {
        text.to_string()
    } else {
        text[..max_len].to_string()
    }
}

impl ApiRequestExecutionConfig {
    fn from_env() -> Self {
        Self {
            prompt_version: env::var("SUMMARY_PROMPT_VERSION").unwrap_or_else(|_| "v1".to_string()),
            enable_chunking: parse_bool_env("CHUNKING_ENABLED", true),
            chunk_max_chars: parse_usize_env("CHUNK_MAX_CHARS", 200_000),
            primary_model: env::var("OPENROUTER_MODEL")
                .unwrap_or_else(|_| "deepseek/deepseek-v3.2".to_string()),
            long_context_model: normalize_optional_env("OPENROUTER_LONG_CONTEXT_MODEL")
                .or_else(|| Some("google/gemini-3-flash-preview".to_string())),
            fallback_models: parse_list_env(
                "OPENROUTER_FALLBACK_MODELS",
                &[
                    "moonshotai/kimi-k2.5",
                    "qwen/qwen3-max",
                    "deepseek/deepseek-r1",
                ],
            ),
            flash_model: normalize_optional_env("OPENROUTER_FLASH_MODEL")
                .or_else(|| Some("google/gemini-3-flash-preview".to_string())),
            flash_fallback_models: parse_list_env(
                "OPENROUTER_FLASH_FALLBACK_MODELS",
                &["anthropic/claude-haiku-4.5"],
            ),
            structured_output_mode: env::var("OPENROUTER_STRUCTURED_OUTPUT_MODE")
                .unwrap_or_else(|_| "json_schema".to_string()),
            temperature: parse_f64_env("OPENROUTER_TEMPERATURE", 0.2),
            top_p: parse_optional_f64_env("OPENROUTER_TOP_P"),
            json_temperature: parse_optional_f64_env("OPENROUTER_SUMMARY_TEMPERATURE_JSON"),
            json_top_p: parse_optional_f64_env("OPENROUTER_SUMMARY_TOP_P_JSON"),
            enable_two_pass_enrichment: parse_bool_env("SUMMARY_TWO_PASS_ENABLED", false),
            execute_inline: parse_bool_env("API_REQUEST_EXECUTOR_INLINE", false),
        }
    }
}

impl TtsRuntimeConfig {
    fn from_env() -> Self {
        Self {
            enabled: parse_bool_env("ELEVENLABS_ENABLED", false),
            api_key: normalize_optional_env("ELEVENLABS_API_KEY"),
            voice_id: env::var("ELEVENLABS_VOICE_ID")
                .unwrap_or_else(|_| "21m00Tcm4TlvDq8ikWAM".to_string()),
            model: env::var("ELEVENLABS_MODEL")
                .unwrap_or_else(|_| "eleven_multilingual_v2".to_string()),
            output_format: env::var("ELEVENLABS_OUTPUT_FORMAT")
                .unwrap_or_else(|_| "mp3_44100_128".to_string()),
            stability: parse_f64_env("ELEVENLABS_STABILITY", 0.5),
            similarity_boost: parse_f64_env("ELEVENLABS_SIMILARITY_BOOST", 0.75),
            speed: parse_f64_env("ELEVENLABS_SPEED", 1.0),
            timeout_sec: parse_f64_env("ELEVENLABS_TIMEOUT_SEC", 60.0),
            max_chars_per_request: parse_usize_env("ELEVENLABS_MAX_CHARS", 5000),
            audio_storage_path: env::var("ELEVENLABS_AUDIO_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/data/audio")),
            base_url: env::var("ELEVENLABS_BASE_URL")
                .unwrap_or_else(|_| "https://api.elevenlabs.io/v1".to_string()),
        }
    }
}

fn parse_bool_env(key: &str, default: bool) -> bool {
    env::var(key)
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

fn parse_usize_env(key: &str, default: usize) -> usize {
    env::var(key)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(default)
}

fn parse_f64_env(key: &str, default: f64) -> f64 {
    env::var(key)
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(default)
}

fn parse_optional_f64_env(key: &str) -> Option<f64> {
    env::var(key)
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
}

fn normalize_optional_env(key: &str) -> Option<String> {
    env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn parse_list_env(key: &str, defaults: &[&str]) -> Vec<String> {
    env::var(key)
        .ok()
        .map(|value| {
            value
                .split(',')
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(str::to_string)
                .collect::<Vec<_>>()
        })
        .filter(|values| !values.is_empty())
        .unwrap_or_else(|| defaults.iter().map(|value| value.to_string()).collect())
}
