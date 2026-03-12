use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::body::Body;
use axum::http::header::{CONTENT_DISPOSITION, CONTENT_TYPE};
use axum::http::{Method, Request, StatusCode};
use axum::routing::post;
use axum::Router;
use bsr_mobile_api::{build_router, build_state, ApiRuntimeConfig};
use chrono::Utc;
use http_body_util::BodyExt;
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use rusqlite::{params, Connection};
use serde::Serialize;
use serde_json::{json, Value};
use serial_test::serial;
use sha2::{Digest, Sha256};
use tokio::net::TcpListener;
use tokio::task::JoinHandle;
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
    std::env::temp_dir().join(format!("bsr-mobile-api-content-{label}-{nanos}.db"))
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
                processing_time_ms INTEGER NULL,
                error_context_json TEXT NULL
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
                tokens_prompt INTEGER NULL,
                tokens_completion INTEGER NULL,
                cost_usd REAL NULL,
                latency_ms INTEGER NULL,
                status TEXT NULL,
                error_text TEXT NULL,
                error_context_json TEXT NULL,
                created_at TEXT NULL,
                updated_at TEXT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL,
                device_id TEXT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_seen_at TEXT NULL,
                created_at TEXT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audio_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id INTEGER NOT NULL UNIQUE,
                provider TEXT NOT NULL,
                voice_id TEXT NOT NULL,
                model TEXT NOT NULL,
                file_path TEXT NULL,
                file_size_bytes INTEGER NULL,
                duration_sec REAL NULL,
                char_count INTEGER NULL,
                source_field TEXT NOT NULL,
                language TEXT NULL,
                status TEXT NOT NULL,
                error_text TEXT NULL,
                latency_ms INTEGER NULL,
                created_at TEXT NULL,
                FOREIGN KEY(summary_id) REFERENCES summaries(id) ON DELETE CASCADE
            );
            "#,
        )
        .expect("create content schema");
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

fn seed_user(path: &Path, telegram_user_id: i64, username: &str) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO users (
                telegram_user_id, username, is_owner, server_version, updated_at, created_at
            ) VALUES (?1, ?2, 0, ?3, ?4, ?4)
            "#,
            params![
                telegram_user_id,
                username,
                Utc::now().timestamp_millis(),
                now
            ],
        )
        .expect("insert user");
}

struct RequestSeed<'a> {
    user_id: i64,
    request_type: &'a str,
    status: &'a str,
    correlation_id: &'a str,
    input_url: Option<&'a str>,
    normalized_url: Option<&'a str>,
    dedupe_hash: Option<&'a str>,
    content_text: Option<&'a str>,
    lang_detected: Option<&'a str>,
    error_context_json: Option<Value>,
    fwd_from_chat_id: Option<i64>,
    fwd_from_msg_id: Option<i64>,
}

fn insert_request(path: &Path, seed: RequestSeed<'_>) -> i64 {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO requests (
                created_at, updated_at, type, status, correlation_id, user_id,
                input_url, normalized_url, dedupe_hash, content_text, lang_detected,
                route_version, error_context_json, fwd_from_chat_id, fwd_from_msg_id
            ) VALUES (?1, ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, 1, ?11, ?12, ?13)
            "#,
            params![
                now,
                seed.request_type,
                seed.status,
                seed.correlation_id,
                seed.user_id,
                seed.input_url,
                seed.normalized_url,
                seed.dedupe_hash,
                seed.content_text,
                seed.lang_detected,
                seed.error_context_json.map(|value| value.to_string()),
                seed.fwd_from_chat_id,
                seed.fwd_from_msg_id,
            ],
        )
        .expect("insert request");
    connection.last_insert_rowid()
}

fn insert_summary(
    path: &Path,
    request_id: i64,
    lang: &str,
    json_payload: &Value,
    is_read: bool,
    is_favorited: bool,
) -> i64 {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO summaries (
                request_id, lang, json_payload, version, server_version,
                is_read, is_favorited, is_deleted, updated_at, created_at
            ) VALUES (?1, ?2, ?3, 1, ?4, ?5, ?6, 0, ?7, ?7)
            "#,
            params![
                request_id,
                lang,
                json_payload.to_string(),
                Utc::now().timestamp_millis(),
                if is_read { 1 } else { 0 },
                if is_favorited { 1 } else { 0 },
                now,
            ],
        )
        .expect("insert summary");
    connection.last_insert_rowid()
}

fn insert_crawl_result(
    path: &Path,
    request_id: i64,
    source_url: Option<&str>,
    content_markdown: Option<&str>,
    content_html: Option<&str>,
    metadata_json: Option<&Value>,
    status: &str,
    error_text: Option<&str>,
) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO crawl_results (
                request_id, source_url, endpoint, http_status, status, options_json,
                correlation_id, content_markdown, content_html, structured_json,
                metadata_json, links_json, firecrawl_success, firecrawl_error_code,
                firecrawl_error_message, firecrawl_details_json, raw_response_json,
                latency_ms, error_text, updated_at, created_at
            ) VALUES (?1, ?2, '/v1/scrape', 200, ?3, NULL, NULL, ?4, ?5, NULL, ?6, NULL, 1, NULL, NULL, NULL, NULL, 120, ?7, ?8, ?8)
            "#,
            params![
                request_id,
                source_url,
                status,
                content_markdown,
                content_html,
                metadata_json.map(Value::to_string),
                error_text,
                now,
            ],
        )
        .expect("insert crawl result");
}

fn insert_llm_call(
    path: &Path,
    request_id: i64,
    model: &str,
    status: &str,
    error_text: Option<&str>,
    error_context_json: Option<&Value>,
) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO llm_calls (
                request_id, provider, model, endpoint, tokens_prompt, tokens_completion,
                cost_usd, latency_ms, status, error_text, error_context_json, created_at, updated_at
            ) VALUES (?1, 'openrouter', ?2, '/chat/completions', 120, 45, 0.0021, 340, ?3, ?4, ?5, ?6, ?6)
            "#,
            params![
                request_id,
                model,
                status,
                error_text,
                error_context_json.map(Value::to_string),
                now,
            ],
        )
        .expect("insert llm call");
}

fn get_device_row(path: &Path, token: &str) -> (String, Option<String>, bool) {
    let connection = Connection::open(path).expect("open sqlite");
    connection
        .query_row(
            "SELECT platform, device_id, is_active FROM user_devices WHERE token = ?1",
            [token],
            |row| Ok((row.get(0)?, row.get(1)?, row.get::<_, bool>(2)?)),
        )
        .expect("device row")
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

async fn read_bytes(response: axum::response::Response) -> Vec<u8> {
    response
        .into_body()
        .collect()
        .await
        .expect("body")
        .to_bytes()
        .to_vec()
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

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

struct EnvGuard {
    saved: Vec<(String, Option<String>)>,
}

impl EnvGuard {
    fn set_many(pairs: &[(&str, &str)]) -> Self {
        let mut saved = Vec::new();
        for (key, value) in pairs {
            saved.push(((*key).to_string(), std::env::var(key).ok()));
            unsafe {
                std::env::set_var(key, value);
            }
        }
        Self { saved }
    }
}

impl Drop for EnvGuard {
    fn drop(&mut self) {
        for (key, value) in self.saved.drain(..).rev() {
            unsafe {
                match value {
                    Some(saved) => std::env::set_var(&key, saved),
                    None => std::env::remove_var(&key),
                }
            }
        }
    }
}

async fn spawn_tts_server(audio_bytes: Vec<u8>) -> (String, JoinHandle<()>) {
    let payload = Arc::new(audio_bytes);
    let app = Router::new().route(
        "/text-to-speech/{voice_id}",
        post({
            let payload = payload.clone();
            move || {
                let payload = payload.clone();
                async move {
                    (
                        [(CONTENT_TYPE, "audio/mpeg")],
                        Body::from((*payload).clone()),
                    )
                }
            }
        }),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind tts");
    let address = listener.local_addr().expect("tts addr");
    let handle = tokio::spawn(async move {
        axum::serve(listener, app).await.expect("tts server");
    });
    (format!("http://{address}"), handle)
}

#[tokio::test]
async fn articles_alias_and_summary_detail_routes_match() {
    let user_id = 123_456_789;
    let config = test_config("alias-detail", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "article_user");

    let request_id = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-article-1",
            input_url: Some("https://example.com/article"),
            normalized_url: Some("https://example.com/article"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/article")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let summary_id = insert_summary(
        &db_path,
        request_id,
        "en",
        &json!({
            "summary_250": "Short summary",
            "summary_1000": "Long summary",
            "tldr": "Too long",
            "key_ideas": ["Idea 1", "Idea 2"],
            "topic_tags": ["tag1", "tag2"],
            "entities": {"people": ["Person"], "organizations": ["Org"], "locations": ["Loc"]},
            "estimated_reading_time_min": 5,
            "key_stats": [{"label": "Stat", "value": 10, "unit": "%", "source_excerpt": "source"}],
            "answered_questions": ["Q1?"],
            "readability": {"method": "FK", "score": 50.0, "level": "Easy"},
            "seo_keywords": ["keyword"],
            "metadata": {
                "title": "Example Article",
                "domain": "example.com",
                "author": "Author",
                "published_at": "2023-01-01"
            },
            "confidence": 0.9,
            "hallucination_risk": "low"
        }),
        false,
        false,
    );
    insert_crawl_result(
        &db_path,
        request_id,
        Some("https://example.com/article"),
        Some("# Heading\n\nBody text."),
        None,
        Some(&json!({"title": "Example Article", "domain": "example.com", "author": "Author"})),
        "success",
        None,
    );
    insert_llm_call(
        &db_path,
        request_id,
        "google/gemini-3-flash-preview",
        "completed",
        None,
        None,
    );

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "article_user");

    let summary_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{summary_id}"),
        &headers,
        None,
    )
    .await;
    assert_eq!(summary_response.status(), StatusCode::OK);
    let summary_payload = read_json(summary_response).await;

    let article_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/articles/{summary_id}"),
        &headers,
        None,
    )
    .await;
    assert_eq!(article_response.status(), StatusCode::OK);
    let article_payload = read_json(article_response).await;

    assert_eq!(
        summary_payload["data"]["summary"]["tldr"],
        json!("Too long")
    );
    assert_eq!(
        article_payload["data"]["summary"]["tldr"],
        summary_payload["data"]["summary"]["tldr"]
    );
    assert_eq!(
        article_payload["data"]["request"]["url"],
        json!("https://example.com/article")
    );

    let by_url_response = send_request(
        &app,
        Method::GET,
        "/v1/articles/by-url?url=https%3A%2F%2Fexample.com%2Farticle",
        &headers,
        None,
    )
    .await;
    assert_eq!(by_url_response.status(), StatusCode::OK);
    let by_url_payload = read_json(by_url_response).await;
    assert_eq!(
        by_url_payload["data"]["request"]["url"],
        json!("https://example.com/article")
    );
}

#[tokio::test]
async fn summary_list_filters_toggle_patch_and_delete_work() {
    let user_id = 111_222_333;
    let config = test_config("summary-list", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "list_user");

    let first_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-list-1",
            input_url: Some("https://example.com/a"),
            normalized_url: Some("https://example.com/a"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/a")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let second_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-list-2",
            input_url: Some("https://example.com/b"),
            normalized_url: Some("https://example.com/b"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/b")),
            content_text: None,
            lang_detected: Some("ru"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let first_summary = insert_summary(
        &db_path,
        first_request,
        "en",
        &json!({"tldr": "A", "summary_250": "A250", "metadata": {"title": "A", "domain": "example.com"}}),
        false,
        true,
    );
    let second_summary = insert_summary(
        &db_path,
        second_request,
        "ru",
        &json!({"tldr": "B", "summary_250": "B250", "metadata": {"title": "B", "domain": "example.com"}}),
        false,
        false,
    );

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "list_user");

    let favorites_response = send_request(
        &app,
        Method::GET,
        "/v1/summaries?is_favorited=true",
        &headers,
        None,
    )
    .await;
    assert_eq!(favorites_response.status(), StatusCode::OK);
    let favorites_payload = read_json(favorites_response).await;
    assert_eq!(
        favorites_payload["data"]["summaries"]
            .as_array()
            .expect("favorites array")
            .len(),
        1
    );
    assert_eq!(
        favorites_payload["data"]["summaries"][0]["id"],
        json!(first_summary)
    );

    let toggle_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/summaries/{second_summary}/favorite"),
        &headers,
        None,
    )
    .await;
    assert_eq!(toggle_response.status(), StatusCode::OK);
    let toggle_payload = read_json(toggle_response).await;
    assert_eq!(toggle_payload["data"]["isFavorited"], json!(true));

    let patch_response = send_request(
        &app,
        Method::PATCH,
        &format!("/v1/summaries/{second_summary}"),
        &headers,
        Some(json!({"is_read": true})),
    )
    .await;
    assert_eq!(patch_response.status(), StatusCode::OK);
    let patch_payload = read_json(patch_response).await;
    assert_eq!(patch_payload["data"]["isRead"], json!(true));

    let delete_response = send_request(
        &app,
        Method::DELETE,
        &format!("/v1/summaries/{first_summary}"),
        &headers,
        None,
    )
    .await;
    assert_eq!(delete_response.status(), StatusCode::OK);

    let deleted_get_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{first_summary}"),
        &headers,
        None,
    )
    .await;
    assert_eq!(deleted_get_response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn summary_content_routes_preserve_markdown_and_html_fallback() {
    let user_id = 444_555_666;
    let config = test_config("summary-content", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "content_user");

    let markdown_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-content-1",
            input_url: Some("https://example.com/markdown"),
            normalized_url: Some("https://example.com/markdown"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/markdown")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let markdown_summary = insert_summary(
        &db_path,
        markdown_request,
        "en",
        &json!({"metadata": {"title": "Markdown Article", "domain": "example.com"}}),
        false,
        false,
    );
    insert_crawl_result(
        &db_path,
        markdown_request,
        Some("https://example.com/markdown"),
        Some("# Heading\n\nBody text."),
        None,
        Some(&json!({"title": "Markdown Article", "domain": "example.com"})),
        "success",
        None,
    );

    let html_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-content-2",
            input_url: Some("https://example.com/html"),
            normalized_url: Some("https://example.com/html"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/html")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let html_summary = insert_summary(
        &db_path,
        html_request,
        "en",
        &json!({"metadata": {"title": "HTML Article", "domain": "example.com"}}),
        false,
        false,
    );
    insert_crawl_result(
        &db_path,
        html_request,
        Some("https://example.com/html"),
        None,
        Some("<h1>Heading</h1><p>Body text.</p>"),
        Some(&json!({"title": "HTML Article", "domain": "example.com"})),
        "success",
        None,
    );

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "content_user");

    let markdown_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{markdown_summary}/content"),
        &headers,
        None,
    )
    .await;
    assert_eq!(markdown_response.status(), StatusCode::OK);
    let markdown_payload = read_json(markdown_response).await;
    assert_eq!(
        markdown_payload["data"]["content"]["format"],
        json!("markdown")
    );
    assert_eq!(
        markdown_payload["data"]["content"]["contentType"],
        json!("text/markdown")
    );

    let markdown_text_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{markdown_summary}/content?format=text"),
        &headers,
        None,
    )
    .await;
    assert_eq!(markdown_text_response.status(), StatusCode::OK);
    let markdown_text_payload = read_json(markdown_text_response).await;
    assert_eq!(
        markdown_text_payload["data"]["content"]["format"],
        json!("text")
    );
    assert!(markdown_text_payload["data"]["content"]["content"]
        .as_str()
        .expect("text content")
        .contains("Body text."));

    let html_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{html_summary}/content"),
        &headers,
        None,
    )
    .await;
    assert_eq!(html_response.status(), StatusCode::OK);
    let html_payload = read_json(html_response).await;
    assert_eq!(html_payload["data"]["content"]["format"], json!("text"));
    assert_eq!(
        html_payload["data"]["content"]["contentType"],
        json!("text/plain")
    );
    assert!(html_payload["data"]["content"]["content"]
        .as_str()
        .expect("html fallback text")
        .contains("Heading Body text."));
}

#[tokio::test]
async fn request_detail_and_status_preserve_flat_contract() {
    let user_id = 777_888_999;
    let config = test_config("request-status", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "status_user");

    let pending_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "pending",
            correlation_id: "cid-pending-1",
            input_url: Some("https://example.com/pending"),
            normalized_url: Some("https://example.com/pending"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/pending")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );

    let error_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "error",
            correlation_id: "cid-error-1",
            input_url: Some("https://example.com/error"),
            normalized_url: Some("https://example.com/error"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/error")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: Some(json!({
                "stage": "extraction",
                "component": "firecrawl",
                "reason_code": "FIRECRAWL_ERROR",
                "error_message": "normalized error",
                "retryable": true,
                "attempt": 1,
                "max_attempts": 3,
                "timestamp": "2026-02-28T10:00:00Z"
            })),
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    insert_llm_call(
        &db_path,
        error_request,
        "google/gemini-3-flash-preview",
        "error",
        Some("llm summary failed"),
        Some(&json!({"status_code": 429, "message": "Rate limit exceeded"})),
    );

    let detail_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-detail-1",
            input_url: Some("https://example.com/detail"),
            normalized_url: Some("https://example.com/detail"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/detail")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let detail_summary = insert_summary(
        &db_path,
        detail_request,
        "en",
        &json!({"tldr": "Detail summary", "metadata": {"title": "Detail"}}),
        false,
        false,
    );
    insert_crawl_result(
        &db_path,
        detail_request,
        Some("https://example.com/detail"),
        Some("Detail body"),
        None,
        Some(&json!({"title": "Detail"})),
        "success",
        None,
    );
    insert_llm_call(
        &db_path,
        detail_request,
        "google/gemini-3-flash-preview",
        "completed",
        None,
        None,
    );

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "status_user");

    let pending_status_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/requests/{pending_request}/status"),
        &headers,
        None,
    )
    .await;
    assert_eq!(pending_status_response.status(), StatusCode::OK);
    let pending_status_payload = read_json(pending_status_response).await;
    assert_eq!(pending_status_payload["data"]["status"], json!("pending"));
    assert_eq!(pending_status_payload["data"]["stage"], json!("pending"));
    assert_eq!(pending_status_payload["data"]["canRetry"], json!(false));
    assert!(pending_status_payload["data"]["status"].is_string());

    let error_status_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/requests/{error_request}/status"),
        &headers,
        None,
    )
    .await;
    assert_eq!(error_status_response.status(), StatusCode::OK);
    let error_status_payload = read_json(error_status_response).await;
    assert_eq!(error_status_payload["data"]["status"], json!("error"));
    assert_eq!(error_status_payload["data"]["stage"], json!("failed"));
    assert_eq!(
        error_status_payload["data"]["errorStage"],
        json!("extraction")
    );
    assert_eq!(
        error_status_payload["data"]["errorReasonCode"],
        json!("FIRECRAWL_ERROR")
    );
    assert_eq!(
        error_status_payload["data"]["errorMessage"],
        json!("normalized error")
    );
    assert_eq!(error_status_payload["data"]["canRetry"], json!(true));

    let detail_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/requests/{detail_request}"),
        &headers,
        None,
    )
    .await;
    assert_eq!(detail_response.status(), StatusCode::OK);
    let detail_payload = read_json(detail_response).await;
    assert_eq!(
        detail_payload["data"]["request"]["id"],
        json!(detail_request)
    );
    assert_eq!(
        detail_payload["data"]["llmCalls"][0]["model"],
        json!("google/gemini-3-flash-preview")
    );
    assert_eq!(
        detail_payload["data"]["summary"]["id"],
        json!(detail_summary)
    );
}

#[tokio::test]
async fn duplicate_submit_and_notification_registration_match_contract() {
    let user_id = 135_792_468;
    let config = test_config("duplicate-device", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "notif_user");

    let normalized_url = "https://example.com/article";
    let request_id = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-dup-1",
            input_url: Some(normalized_url),
            normalized_url: Some(normalized_url),
            dedupe_hash: Some(&sha256_hex(normalized_url.as_bytes())),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let summary_id = insert_summary(
        &db_path,
        request_id,
        "en",
        &json!({"tldr": "Cached", "metadata": {"title": "Cached"}}),
        false,
        false,
    );

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "notif_user");

    let duplicate_response = send_request(
        &app,
        Method::POST,
        "/v1/requests",
        &headers,
        Some(json!({
            "type": "url",
            "input_url": normalized_url,
            "lang_preference": "en"
        })),
    )
    .await;
    assert_eq!(duplicate_response.status(), StatusCode::OK);
    let duplicate_payload = read_json(duplicate_response).await;
    assert_eq!(duplicate_payload["data"]["isDuplicate"], json!(true));
    assert_eq!(
        duplicate_payload["data"]["existingRequestId"],
        json!(request_id)
    );
    assert_eq!(
        duplicate_payload["data"]["existingSummaryId"],
        json!(summary_id)
    );

    let first_device_response = send_request(
        &app,
        Method::POST,
        "/v1/notifications/device",
        &headers,
        Some(json!({
            "token": "fcm_token_123",
            "platform": "android",
            "device_id": "device_123"
        })),
    )
    .await;
    assert_eq!(first_device_response.status(), StatusCode::OK);
    let first_device_payload = read_json(first_device_response).await;
    assert_eq!(first_device_payload, json!({"status": "ok"}));

    let update_device_response = send_request(
        &app,
        Method::POST,
        "/v1/notifications/device",
        &headers,
        Some(json!({
            "token": "fcm_token_123",
            "platform": "android",
            "device_id": "device_456"
        })),
    )
    .await;
    assert_eq!(update_device_response.status(), StatusCode::OK);
    let device_row = get_device_row(&db_path, "fcm_token_123");
    assert_eq!(device_row.0, "android");
    assert_eq!(device_row.1.as_deref(), Some("device_456"));
    assert!(device_row.2);
}

#[tokio::test]
async fn proxy_route_rejects_ssrf_targets() {
    let user_id = 909_101_102;
    let config = test_config("proxy-ssrf", HashSet::from([user_id]));
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    let headers = auth_headers(&secret, user_id, "proxy_user");
    let app = build_test_app(config).await;

    let response = send_request(
        &app,
        Method::GET,
        "/v1/proxy/image?url=http%3A%2F%2F127.0.0.1%3A8080%2Fimage.jpg",
        &headers,
        None,
    )
    .await;
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    let payload = read_json(response).await;
    assert_eq!(payload["error"]["code"], json!("FORBIDDEN"));
}

#[tokio::test]
#[serial]
async fn retry_and_tts_routes_execute_on_rust_path() {
    let user_id = 246_813_579;
    let config = test_config("retry-tts", HashSet::from([user_id]));
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, user_id, "tts_user");

    let retry_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "error",
            correlation_id: "cid-retry-1",
            input_url: Some("https://example.com/retry"),
            normalized_url: Some("https://example.com/retry"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/retry")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: Some(json!({"stage": "background_execution", "retryable": true})),
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );

    let tts_request = insert_request(
        &db_path,
        RequestSeed {
            user_id,
            request_type: "url",
            status: "ok",
            correlation_id: "cid-tts-1",
            input_url: Some("https://example.com/tts"),
            normalized_url: Some("https://example.com/tts"),
            dedupe_hash: Some(&sha256_hex(b"https://example.com/tts")),
            content_text: None,
            lang_detected: Some("en"),
            error_context_json: None,
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
        },
    );
    let tts_summary = insert_summary(
        &db_path,
        tts_request,
        "en",
        &json!({
            "summary_1000": "This is the summary text for audio generation.",
            "tldr": "Short audio",
            "metadata": {"title": "Audio"}
        }),
        false,
        false,
    );

    let audio_bytes = b"fake-mp3-data".to_vec();
    let (tts_base_url, tts_handle) = spawn_tts_server(audio_bytes.clone()).await;
    let audio_dir = std::env::temp_dir().join(format!(
        "bsr-audio-{}",
        Utc::now().timestamp_nanos_opt().unwrap_or_default()
    ));
    let audio_dir_string = audio_dir.to_string_lossy().to_string();
    let _env = EnvGuard::set_many(&[
        ("FIRECRAWL_SELF_HOSTED_URL", "http://127.0.0.1:1"),
        ("ELEVENLABS_ENABLED", "1"),
        ("ELEVENLABS_API_KEY", "test-key"),
        ("ELEVENLABS_BASE_URL", tts_base_url.as_str()),
        ("ELEVENLABS_AUDIO_PATH", audio_dir_string.as_str()),
    ]);

    let app = build_test_app(config).await;
    let headers = auth_headers(&secret, user_id, "tts_user");

    let retry_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/requests/{retry_request}/retry"),
        &headers,
        None,
    )
    .await;
    assert_eq!(retry_response.status(), StatusCode::OK);
    let retry_payload = read_json(retry_response).await;
    assert_eq!(retry_payload["data"]["status"], json!("pending"));
    assert!(retry_payload["data"]["correlationId"]
        .as_str()
        .expect("correlation id")
        .ends_with("-retry-1"));

    let generate_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/summaries/{tts_summary}/audio"),
        &headers,
        None,
    )
    .await;
    assert_eq!(generate_response.status(), StatusCode::OK);
    let generate_payload = read_json(generate_response).await;
    assert_eq!(generate_payload["data"]["status"], json!("completed"));
    assert_eq!(
        generate_payload["data"]["fileSizeBytes"],
        json!(audio_bytes.len())
    );

    let get_audio_response = send_request(
        &app,
        Method::GET,
        &format!("/v1/summaries/{tts_summary}/audio"),
        &headers,
        None,
    )
    .await;
    assert_eq!(get_audio_response.status(), StatusCode::OK);
    assert_eq!(
        get_audio_response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok()),
        Some("audio/mpeg")
    );
    let expected_content_disposition =
        format!("attachment; filename=\"summary-{tts_summary}.mp3\"");
    assert_eq!(
        get_audio_response
            .headers()
            .get(CONTENT_DISPOSITION)
            .and_then(|value| value.to_str().ok()),
        Some(expected_content_disposition.as_str())
    );
    let body = read_bytes(get_audio_response).await;
    assert_eq!(body, audio_bytes);

    tts_handle.abort();
}
