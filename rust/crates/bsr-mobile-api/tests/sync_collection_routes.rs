use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use axum::Router;
use bsr_mobile_api::{build_router, build_state, ApiRuntimeConfig};
use chrono::Utc;
use http_body_util::BodyExt;
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use rusqlite::{params, Connection};
use serde::Serialize;
use serde_json::{json, Value};
use tower::ServiceExt;

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn unique_db_path(label: &str) -> PathBuf {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or_default();
    std::env::temp_dir().join(format!("bsr-mobile-api-sync-collections-{label}-{nanos}.db"))
}

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339()
}

fn init_sqlite_schema(path: &Path) {
    let connection = Connection::open(path).expect("open test sqlite");
    connection
        .execute_batch(
            r#"
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT NULL,
                is_owner INTEGER NOT NULL DEFAULT 0,
                preferences_json TEXT NULL,
                linked_telegram_user_id INTEGER NULL,
                linked_telegram_username TEXT NULL,
                linked_telegram_photo_url TEXT NULL,
                linked_telegram_first_name TEXT NULL,
                linked_telegram_last_name TEXT NULL,
                linked_at TEXT NULL,
                link_nonce TEXT NULL,
                link_nonce_expires_at TEXT NULL,
                server_version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                type TEXT NULL,
                status TEXT NULL,
                correlation_id TEXT NULL,
                chat_id INTEGER NULL,
                user_id INTEGER NULL,
                input_url TEXT NULL,
                normalized_url TEXT NULL,
                dedupe_hash TEXT NULL,
                input_message_id INTEGER NULL,
                fwd_from_chat_id INTEGER NULL,
                fwd_from_msg_id INTEGER NULL,
                lang_detected TEXT NULL,
                content_text TEXT NULL,
                route_version INTEGER NOT NULL DEFAULT 1,
                server_version INTEGER NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                error_type TEXT NULL,
                error_message TEXT NULL,
                error_timestamp TEXT NULL,
                processing_time_ms INTEGER NULL,
                error_context_json TEXT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL UNIQUE,
                lang TEXT NULL,
                json_payload TEXT NULL,
                insights_json TEXT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                server_version INTEGER NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_favorited INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS crawl_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                source_url TEXT NULL,
                endpoint TEXT NULL,
                http_status INTEGER NULL,
                status TEXT NULL,
                options_json TEXT NULL,
                correlation_id TEXT NULL,
                content_markdown TEXT NULL,
                content_html TEXT NULL,
                structured_json TEXT NULL,
                metadata_json TEXT NULL,
                links_json TEXT NULL,
                firecrawl_success INTEGER NULL,
                firecrawl_error_code TEXT NULL,
                firecrawl_error_message TEXT NULL,
                firecrawl_details_json TEXT NULL,
                raw_response_json TEXT NULL,
                latency_ms INTEGER NULL,
                error_text TEXT NULL,
                server_version INTEGER NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                updated_at TEXT NULL,
                created_at TEXT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                provider TEXT NULL,
                model TEXT NULL,
                endpoint TEXT NULL,
                request_headers_json TEXT NULL,
                request_messages_json TEXT NULL,
                response_text TEXT NULL,
                response_json TEXT NULL,
                openrouter_response_text TEXT NULL,
                openrouter_response_json TEXT NULL,
                tokens_prompt INTEGER NULL,
                tokens_completion INTEGER NULL,
                cost_usd REAL NULL,
                latency_ms INTEGER NULL,
                status TEXT NULL,
                error_text TEXT NULL,
                structured_output_used INTEGER NULL,
                structured_output_mode TEXT NULL,
                error_context_json TEXT NULL,
                created_at TEXT NULL,
                updated_at TEXT NULL,
                server_version INTEGER NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NULL,
                parent_id INTEGER NULL,
                position INTEGER NULL,
                server_version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_shared INTEGER NOT NULL DEFAULT 0,
                share_count INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                FOREIGN KEY(parent_id) REFERENCES collections(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS collection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                summary_id INTEGER NOT NULL,
                position INTEGER NULL,
                created_at TEXT NOT NULL,
                UNIQUE(collection_id, summary_id),
                FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY(summary_id) REFERENCES summaries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS collection_collaborators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                invited_by_id INTEGER NULL,
                server_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(collection_id, user_id),
                FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE,
                FOREIGN KEY(invited_by_id) REFERENCES users(telegram_user_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS collection_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                expires_at TEXT NULL,
                used_at TEXT NULL,
                invited_email TEXT NULL,
                invited_user_id INTEGER NULL,
                status TEXT NOT NULL DEFAULT 'active',
                server_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
            );
            "#,
        )
        .expect("create sync/collection schema");
}

fn test_config(label: &str, allowed_user_ids: HashSet<i64>) -> ApiRuntimeConfig {
    let db_path = unique_db_path(label);
    init_sqlite_schema(&db_path);
    ApiRuntimeConfig {
        host: "127.0.0.1".to_string(),
        port: 18000,
        db_path,
        allowed_origins: vec!["http://localhost:3000".to_string()],
        openapi_yaml_path: project_root()
            .join("docs")
            .join("openapi")
            .join("mobile_api.yaml"),
        static_dir: project_root().join("app").join("static"),
        app_version: "1.0.0".to_string(),
        app_build: Some("test-build".to_string()),
        jwt_secret_key: Some("0123456789abcdef0123456789abcdef".to_string()),
        bot_token: Some("123456:ABCDEF".to_string()),
        allowed_user_ids,
        allowed_client_ids: HashSet::from([
            "test-client".to_string(),
            "webapp".to_string(),
            "android.app".to_string(),
        ]),
        api_rate_limit_window_seconds: 60,
        api_rate_limit_cooldown_multiplier: 2.0,
        api_rate_limit_default: 100,
        api_rate_limit_summaries: 200,
        api_rate_limit_requests: 10,
        api_rate_limit_search: 50,
        sync_expiry_hours: 1,
        sync_default_limit: 200,
        sync_min_limit: 1,
        sync_max_limit: 500,
        redis_enabled: false,
        redis_required: false,
        redis_url: None,
        redis_host: "127.0.0.1".to_string(),
        redis_port: 6379,
        redis_db: 0,
        redis_password: None,
        redis_prefix: format!("bsr-{label}"),
        secret_login_enabled: true,
        secret_min_length: 12,
        secret_max_length: 128,
        secret_max_failed_attempts: 2,
        secret_lockout_minutes: 1,
        secret_pepper: Some("secret-pepper-value".to_string()),
        apple_jwks_url: "http://127.0.0.1:9/apple".to_string(),
        google_jwks_url: "http://127.0.0.1:9/google".to_string(),
    }
}

async fn build_test_app(config: ApiRuntimeConfig) -> Router {
    let state = build_state(config).await.expect("build state");
    build_router(state.clone()).with_state(state)
}

fn seed_user(path: &Path, telegram_user_id: i64, username: &str, is_owner: bool) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO users (
                telegram_user_id, username, is_owner, server_version, updated_at, created_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?5)
            "#,
            params![
                telegram_user_id,
                username,
                if is_owner { 1 } else { 0 },
                telegram_user_id,
                now,
            ],
        )
        .expect("insert user");
}

fn seed_request(path: &Path, id: i64, user_id: i64, url: &str, status: &str, server_version: i64) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO requests (
                id, created_at, updated_at, type, status, correlation_id, user_id,
                input_url, normalized_url, dedupe_hash, lang_detected, route_version,
                server_version, is_deleted
            ) VALUES (?1, ?2, ?2, 'url', ?3, ?4, ?5, ?6, ?6, ?7, 'en', 1, ?8, 0)
            "#,
            params![
                id,
                now,
                status,
                format!("cid-{id}"),
                user_id,
                url,
                format!("hash-{id}"),
                server_version,
            ],
        )
        .expect("insert request");
}

fn seed_summary(
    path: &Path,
    id: i64,
    request_id: i64,
    is_read: bool,
    is_deleted: bool,
    server_version: i64,
) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO summaries (
                id, request_id, lang, json_payload, insights_json, version, server_version,
                is_read, is_favorited, is_deleted, deleted_at, updated_at, created_at
            ) VALUES (?1, ?2, 'en', ?3, NULL, 1, ?4, ?5, 0, ?6, ?7, ?8, ?8)
            "#,
            params![
                id,
                request_id,
                json!({
                    "summary_250": format!("Summary {id}"),
                    "summary_1000": format!("Long summary {id}"),
                    "tldr": format!("TLDR {id}"),
                    "key_ideas": [format!("Idea {id}")],
                    "topic_tags": ["rust", "migration"],
                    "entities": {
                        "people": [],
                        "organizations": [],
                        "locations": []
                    },
                    "estimated_reading_time_min": 4,
                    "key_stats": [],
                    "answered_questions": [],
                    "seo_keywords": [],
                    "metadata": {
                        "title": format!("Article {id}"),
                        "domain": "example.com",
                    },
                    "confidence": 0.85,
                    "hallucination_risk": "low",
                })
                .to_string(),
                server_version,
                if is_read { 1 } else { 0 },
                if is_deleted { 1 } else { 0 },
                if is_deleted { Some(now.clone()) } else { None::<String> },
                now,
            ],
        )
        .expect("insert summary");
}

fn seed_crawl_result(path: &Path, request_id: i64, server_version: i64) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO crawl_results (
                request_id, source_url, endpoint, http_status, status, content_markdown,
                metadata_json, latency_ms, server_version, is_deleted, updated_at, created_at
            ) VALUES (?1, ?2, '/v1/scrape', 200, 'success', ?3, ?4, 120, ?5, 0, ?6, ?6)
            "#,
            params![
                request_id,
                format!("https://example.com/{request_id}"),
                format!("# Heading {request_id}\n\nBody"),
                json!({"title": format!("Article {request_id}")}).to_string(),
                server_version,
                now,
            ],
        )
        .expect("insert crawl result");
}

fn seed_llm_call(path: &Path, request_id: i64, server_version: i64) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO llm_calls (
                request_id, provider, model, endpoint, tokens_prompt, tokens_completion,
                cost_usd, latency_ms, status, created_at, updated_at, server_version, is_deleted
            ) VALUES (?1, 'openrouter', 'google/gemini-3-flash-preview', '/chat/completions',
                      120, 45, 0.0021, 340, 'completed', ?2, ?2, ?3, 0)
            "#,
            params![request_id, now, server_version],
        )
        .expect("insert llm call");
}

fn seed_collection(
    path: &Path,
    id: i64,
    user_id: i64,
    name: &str,
    parent_id: Option<i64>,
    position: i64,
    is_shared: bool,
    share_count: i64,
    server_version: i64,
) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO collections (
                id, user_id, name, description, parent_id, position, server_version,
                updated_at, created_at, is_shared, share_count, is_deleted, deleted_at
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?8, ?9, ?10, 0, NULL)
            "#,
            params![
                id,
                user_id,
                name,
                format!("{name} description"),
                parent_id,
                position,
                server_version,
                now,
                if is_shared { 1 } else { 0 },
                share_count,
            ],
        )
        .expect("insert collection");
}

fn read_summary_flags(path: &Path, summary_id: i64) -> (bool, bool) {
    let connection = Connection::open(path).expect("open sqlite");
    connection
        .query_row(
            "SELECT is_read, is_deleted FROM summaries WHERE id = ?1",
            [summary_id],
            |row| Ok((row.get::<_, bool>(0)?, row.get::<_, bool>(1)?)),
        )
        .expect("summary flags")
}

fn read_item_positions(path: &Path, collection_id: i64) -> Vec<(i64, i64)> {
    let connection = Connection::open(path).expect("open sqlite");
    let mut statement = connection
        .prepare(
            "SELECT summary_id, position FROM collection_items WHERE collection_id = ?1 ORDER BY position, summary_id",
        )
        .expect("prepare positions");
    let rows = statement
        .query_map([collection_id], |row| Ok((row.get(0)?, row.get(1)?)))
        .expect("query positions");
    rows.map(|row| row.expect("row")).collect()
}

fn collection_share_count(path: &Path, collection_id: i64) -> i64 {
    let connection = Connection::open(path).expect("open sqlite");
    connection
        .query_row(
            "SELECT share_count FROM collections WHERE id = ?1",
            [collection_id],
            |row| row.get(0),
        )
        .expect("collection share count")
}

fn encode_access_jwt(secret: &str, user_id: i64, username: &str, client_id: &str) -> String {
    #[derive(Serialize)]
    struct AccessClaims<'a> {
        user_id: i64,
        username: &'a str,
        client_id: &'a str,
        #[serde(rename = "type")]
        token_type: &'a str,
        exp: i64,
        iat: i64,
    }

    let now = Utc::now().timestamp();
    jsonwebtoken::encode(
        &Header::new(Algorithm::HS256),
        &AccessClaims {
            user_id,
            username,
            client_id,
            token_type: "access",
            exp: now + 300,
            iat: now,
        },
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .expect("encode access token")
}

async fn send_request(
    app: &Router,
    method: Method,
    uri: &str,
    headers: &[(&str, String)],
    body: Option<Value>,
) -> axum::response::Response {
    let mut builder = Request::builder().method(method).uri(uri);
    for (name, value) in headers {
        builder = builder.header(*name, value);
    }
    let request = if let Some(body) = body {
        builder
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .expect("json request")
    } else {
        builder.body(Body::empty()).expect("empty request")
    };
    app.clone().oneshot(request).await.expect("response")
}

async fn read_json(response: axum::response::Response) -> Value {
    let body = response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes();
    serde_json::from_slice(&body).expect("json body")
}

fn auth_headers(secret: &str, user_id: i64, username: &str) -> Vec<(&'static str, String)> {
    vec![(
        "Authorization",
        format!(
            "Bearer {}",
            encode_access_jwt(secret, user_id, username, "test-client")
        ),
    )]
}

#[tokio::test]
async fn collection_routes_cover_tree_acl_and_invites() {
    let config = test_config("collections-tree", HashSet::from([101_i64, 102, 103]));
    let db_path = config.db_path.clone();
    let jwt_secret = config.jwt_secret_key.clone().expect("jwt secret");

    seed_user(&db_path, 101, "owner", false);
    seed_user(&db_path, 102, "editor", false);
    seed_user(&db_path, 103, "invitee", false);

    let app = build_test_app(config).await;

    let create_response = send_request(
        &app,
        Method::POST,
        "/v1/collections",
        &auth_headers(&jwt_secret, 101, "owner"),
        Some(json!({"name": "Root", "description": "Shared root"})),
    )
    .await;
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_payload = read_json(create_response).await;
    let root_id = create_payload["data"]["id"].as_i64().expect("root id");

    let child_response = send_request(
        &app,
        Method::POST,
        "/v1/collections",
        &auth_headers(&jwt_secret, 101, "owner"),
        Some(json!({"name": "Child", "parent_id": root_id, "position": 1})),
    )
    .await;
    assert_eq!(child_response.status(), StatusCode::OK);

    let share_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/collections/{root_id}/share"),
        &auth_headers(&jwt_secret, 101, "owner"),
        Some(json!({"user_id": 102, "role": "editor"})),
    )
    .await;
    assert_eq!(share_response.status(), StatusCode::OK);
    assert_eq!(collection_share_count(&db_path, root_id), 1);

    let acl_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/collections/{root_id}/acl"),
        &auth_headers(&jwt_secret, 101, "owner"),
        None,
    )
    .await;
    assert_eq!(acl_response.status(), StatusCode::OK);
    let acl_payload = read_json(acl_response).await;
    assert_eq!(acl_payload["data"]["acl"].as_array().map(Vec::len), Some(2));

    let tree_response = send_request(
        &app,
        Method::GET,
        "/v1/collections/tree?max_depth=3",
        &auth_headers(&jwt_secret, 101, "owner"),
        None,
    )
    .await;
    assert_eq!(tree_response.status(), StatusCode::OK);
    let tree_payload = read_json(tree_response).await;
    let collections = tree_payload["data"]["collections"]
        .as_array()
        .expect("tree collections");
    assert_eq!(collections.len(), 1);
    assert_eq!(collections[0]["name"], "Root");
    assert_eq!(collections[0]["children"][0]["name"], "Child");

    let invite_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/collections/{root_id}/invite"),
        &auth_headers(&jwt_secret, 101, "owner"),
        Some(json!({"role": "viewer"})),
    )
    .await;
    assert_eq!(invite_response.status(), StatusCode::OK);
    let invite_payload = read_json(invite_response).await;
    let invite_token = invite_payload["data"]["token"].as_str().expect("invite token");

    let accept_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/collections/invites/{invite_token}/accept"),
        &auth_headers(&jwt_secret, 103, "invitee"),
        None,
    )
    .await;
    assert_eq!(accept_response.status(), StatusCode::OK);

    let invited_get = send_request(
        &app,
        Method::GET,
        &format!("/v1/collections/{root_id}"),
        &auth_headers(&jwt_secret, 103, "invitee"),
        None,
    )
    .await;
    assert_eq!(invited_get.status(), StatusCode::OK);
}

#[tokio::test]
async fn collection_item_routes_reorder_move_and_remove() {
    let config = test_config("collections-items", HashSet::from([201_i64]));
    let db_path = config.db_path.clone();
    let jwt_secret = config.jwt_secret_key.clone().expect("jwt secret");

    seed_user(&db_path, 201, "owner", false);
    seed_request(&db_path, 1, 201, "https://example.com/a", "completed", 10);
    seed_request(&db_path, 2, 201, "https://example.com/b", "completed", 11);
    seed_summary(&db_path, 1, 1, false, false, 100);
    seed_summary(&db_path, 2, 2, false, false, 101);
    seed_collection(&db_path, 1, 201, "Source", None, 1, false, 0, 50);
    seed_collection(&db_path, 2, 201, "Target", None, 2, false, 0, 51);

    let app = build_test_app(config).await;
    let headers = auth_headers(&jwt_secret, 201, "owner");

    let add_first = send_request(
        &app,
        Method::POST,
        "/v1/collections/1/items",
        &headers,
        Some(json!({"summary_id": 1})),
    )
    .await;
    assert_eq!(add_first.status(), StatusCode::OK);

    let add_second = send_request(
        &app,
        Method::POST,
        "/v1/collections/1/items",
        &headers,
        Some(json!({"summary_id": 2})),
    )
    .await;
    assert_eq!(add_second.status(), StatusCode::OK);

    let list_response = send_request(
        &app,
        Method::GET,
        "/v1/collections/1/items?limit=50&offset=0",
        &headers,
        None,
    )
    .await;
    assert_eq!(list_response.status(), StatusCode::OK);
    let list_payload = read_json(list_response).await;
    assert_eq!(list_payload["data"]["items"].as_array().map(Vec::len), Some(2));

    let reorder_response = send_request(
        &app,
        Method::POST,
        "/v1/collections/1/items/reorder",
        &headers,
        Some(json!({
            "items": [
                {"summary_id": 2, "position": 1},
                {"summary_id": 1, "position": 2}
            ]
        })),
    )
    .await;
    assert_eq!(reorder_response.status(), StatusCode::OK);
    assert_eq!(read_item_positions(&db_path, 1), vec![(2, 1), (1, 2)]);

    let move_response = send_request(
        &app,
        Method::POST,
        "/v1/collections/1/items/move",
        &headers,
        Some(json!({
            "summary_ids": [2],
            "target_collection_id": 2,
            "position": 1
        })),
    )
    .await;
    assert_eq!(move_response.status(), StatusCode::OK);
    let move_payload = read_json(move_response).await;
    assert_eq!(move_payload["data"]["movedSummaryIds"], json!([2]));
    assert_eq!(read_item_positions(&db_path, 2), vec![(2, 1)]);

    let remove_response = send_request(
        &app,
        Method::DELETE,
        "/v1/collections/2/items/2",
        &headers,
        None,
    )
    .await;
    assert_eq!(remove_response.status(), StatusCode::OK);
    assert!(read_item_positions(&db_path, 2).is_empty());
}

#[tokio::test]
async fn sync_routes_cover_session_full_delta_and_apply() {
    let config = test_config("sync-routes", HashSet::from([301_i64, 302]));
    let db_path = config.db_path.clone();
    let jwt_secret = config.jwt_secret_key.clone().expect("jwt secret");

    seed_user(&db_path, 301, "sync-owner", false);
    seed_user(&db_path, 302, "other-user", false);
    seed_request(&db_path, 1, 301, "https://example.com/one", "completed", 10);
    seed_request(&db_path, 2, 301, "https://example.com/two", "pending", 20);
    seed_summary(&db_path, 1, 1, false, false, 30);
    seed_summary(&db_path, 2, 2, false, true, 31);
    seed_crawl_result(&db_path, 1, 40);
    seed_llm_call(&db_path, 1, 50);

    let app = build_test_app(config).await;
    let headers = auth_headers(&jwt_secret, 301, "sync-owner");

    let session_response = send_request(
        &app,
        Method::POST,
        "/v1/sync/sessions",
        &headers,
        Some(json!({"limit": 2})),
    )
    .await;
    assert_eq!(session_response.status(), StatusCode::OK);
    let session_payload = read_json(session_response).await;
    let session_id = session_payload["data"]["sessionId"]
        .as_str()
        .expect("session id")
        .to_string();
    assert_eq!(session_payload["meta"]["pagination"]["limit"], 200);

    let full_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/sync/full?session_id={session_id}&limit=2"),
        &headers,
        None,
    )
    .await;
    assert_eq!(full_response.status(), StatusCode::OK);
    let full_payload = read_json(full_response).await;
    assert_eq!(full_payload["data"]["sessionId"], session_id);
    assert_eq!(full_payload["data"]["items"].as_array().map(Vec::len), Some(2));
    assert_eq!(full_payload["meta"]["pagination"]["limit"], 2);

    let delta_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/sync/delta?session_id={session_id}&since=0&limit=10"),
        &headers,
        None,
    )
    .await;
    assert_eq!(delta_response.status(), StatusCode::OK);
    let delta_payload = read_json(delta_response).await;
    assert_eq!(delta_payload["data"]["updated"], json!([]));
    assert!(
        delta_payload["data"]["created"]
            .as_array()
            .is_some_and(|records| !records.is_empty())
    );
    assert!(
        delta_payload["data"]["deleted"]
            .as_array()
            .is_some_and(|records| !records.is_empty())
    );

    let apply_response = send_request(
        &app,
        Method::POST,
        "/v1/sync/apply",
        &headers,
        Some(json!({
            "session_id": session_id,
            "changes": [
                {
                    "entity_type": "summary",
                    "id": 1,
                    "action": "update",
                    "last_seen_version": 30,
                    "payload": {"is_read": true}
                },
                {
                    "entity_type": "summary",
                    "id": 2,
                    "action": "delete",
                    "last_seen_version": 31,
                    "payload": {}
                },
                {
                    "entity_type": "request",
                    "id": 1,
                    "action": "update",
                    "last_seen_version": 10,
                    "payload": {}
                }
            ]
        })),
    )
    .await;
    assert_eq!(apply_response.status(), StatusCode::OK);
    let apply_payload = read_json(apply_response).await;
    assert_eq!(apply_payload["data"]["results"].as_array().map(Vec::len), Some(3));
    assert_eq!(apply_payload["data"]["results"][0]["status"], "applied");
    assert_eq!(apply_payload["data"]["results"][1]["status"], "applied");
    assert_eq!(apply_payload["data"]["results"][2]["status"], "invalid");

    assert_eq!(read_summary_flags(&db_path, 1), (true, false));
    assert_eq!(read_summary_flags(&db_path, 2), (false, true));

    let forbidden_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/sync/full?session_id={session_id}"),
        &auth_headers(&jwt_secret, 302, "other-user"),
        None,
    )
    .await;
    assert_eq!(forbidden_response.status(), StatusCode::FORBIDDEN);
}
