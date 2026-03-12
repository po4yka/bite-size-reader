use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::body::Body;
use axum::http::{Method, Request, StatusCode};
use axum::routing::get;
use axum::{Json, Router};
use bsr_mobile_api::{build_router, build_state, ApiRuntimeConfig};
use chrono::Utc;
use hmac::{Hmac, Mac};
use http_body_util::BodyExt;
use jsonwebtoken::{Algorithm, EncodingKey, Header};
use rusqlite::{params, Connection};
use serde::Serialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio::net::TcpListener;
use tokio::task::JoinHandle;
use tower::ServiceExt;
use url::form_urlencoded;

type HmacSha256 = Hmac<Sha256>;

const TEST_OAUTH_KID: &str = "test-jwks-kid";
const TEST_OAUTH_JWK_N: &str = "wtVdPWXjBmw1Ey3QQGoJdVuc2dNseuItIbglJ-babSB8Xwr3b6PHmdyuSGaLyzEqbJhX2OxiDzk995TlbXwaS5LcE0mXYmFFAhFUt6Sag3c59hAWK9Bnxv2CSSsC4aIxwArTmXxgO0UoN_-bgLRq-p6Tw9jvsZuapQTRPjSuvvzr1nPPB_IvCQSOF_nh-vkesE2n-G0itJteYEtz2YVGgT2Ynqrnh7qA2k9RPmJ1dAy05Vo4U3-Y7qodMU8igas3SYVZlqqm3yFOwly33lttAoibdwLz7std0Xjva8r5vtUlO4yGAnj2Bi4C4JTBxU2HMEZd6FZkhPSH0YxFJN2d4Q";
const TEST_OAUTH_JWK_E: &str = "AQAB";
const TEST_OAUTH_PRIVATE_KEY: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDC1V09ZeMGbDUT
LdBAagl1W5zZ02x64i0huCUn5tptIHxfCvdvo8eZ3K5IZovLMSpsmFfY7GIPOT33
lOVtfBpLktwTSZdiYUUCEVS3pJqDdzn2EBYr0GfG/YJJKwLhojHACtOZfGA7RSg3
/5uAtGr6npPD2O+xm5qlBNE+NK6+/OvWc88H8i8JBI4X+eH6+R6wTaf4bSK0m15g
S3PZhUaBPZiequeHuoDaT1E+YnV0DLTlWjhTf5juqh0xTyKBqzdJhVmWqqbfIU7C
XLfeW20CiJt3AvPuy13ReO9ryvm+1SU7jIYCePYGLgLglMHFTYcwRl3oVmSE9IfR
jEUk3Z3hAgMBAAECggEAWtTxGrI49KIW3mGh8J3e2f1Dc1P7g5CVfN5mSCN6mpym
DwNEVyJSaHt3Lx7Ltoet4SHm9qVBlBpaNuYOTgwpECmf+0f4US/K5cthpRoSxQ6d
EYfvZi7Lavx+NJFeTwX4TrFdc/WFwawcs3qxqv+xzjSG7Cvjl3hVUPCdgnQ6MaRU
4sCk2XLjw8XMzZk4MfB8fBg6VV7ND6gDWaEjP0jEKwbd4KpU+9DXboe+/1zNC3tP
PE0cdaEGrBKvjew6OZqprwepnkY2s391oIxqa3wiNhvZYhEu3RnEniouf6Ifl1yj
zNpyY0+k9+oMK734YhJatAgMniqR3iNhcE9di0X+5wKBgQDrT8Br6Pva03cDUeam
U4JrwEysp1vfiTvac4U1qWgdt3j/szPJ2M4XT96zG+amoHeHaft+SP52vGjruMf0
/Ru2n82g5wSQhhhryLmL7ZnB3lpU4fzdnvwQqSu5XR9lLqV+im4KxcAfREb7ZDm6
N818nZM86IlPHxDL32i8waoIRwKBgQDT9o6GJ+ih0OLLkUJvuPgzlYdClM3kxlu7
dlQO9BNthU8i8mBB6nsnmeOKVKP2vY93Ofzegewwww2ar52tfODQ3v7Fnoc5cdBC
AKvFzv5xLehxcKr4CGR2UY5YnfMv+OoRiJORcnRj/TPw8/Cm4wUggnJwhjcu8Fm4
BNEQ8XFklwKBgC0rLeCI5G9o0BuPCRs8RHiyfQVXSsdp7FdOfW+DiTzLDyrmFzbT
qxvGdRUkce3iN4+CxIfFMzNPj0RQP/HC9CLmIe6U6cdkNiPab+NwRGd2axiIGKXh
8riwAHiga3pcrd/QarcepnZaANYYswwP0h3tkWnLqS/K4sp/o/c3pY/ZAoGAJHqn
dsFBkS/RCHXceDveQ4p1d+kCMmBNA0tPFi+9dDjgMMSD+nQvc9ZRScpdWaawHTXW
pji3/IBlQ/z7ZxM54divAjXRUfqbe/B/n5CLS9E50uQwGHXhTFem5utwIg51wkS+
GOcYzuiR2uMwxJgHltu8dE81ChgFaN0zWfYjrMsCgYAc3GfnpcYEa7inbfI/7VE+
j4YhV7gy4kWow+lafpIE5IOF+QeeN9aK+xtnPgJxKc2P33ysWNQcGXNKscERoAj/
NtwKSxt31wnd61otVzPkp3nLyu11g4Zjrc9QFFM/Lq3ycjDdS+duPKFZzwwdVp3M
guKBo4fZglLxStNAFb+jAQ==
-----END PRIVATE KEY-----
"#;

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
    std::env::temp_dir().join(format!("bsr-mobile-api-core-{label}-{nanos}.db"))
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

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL,
                client_id TEXT NULL,
                device_info TEXT NULL,
                ip_address TEXT NULL,
                is_revoked INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT NOT NULL,
                last_used_at TEXT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS client_secrets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                secret_hash TEXT NOT NULL,
                secret_salt TEXT NOT NULL,
                status TEXT NOT NULL,
                label TEXT NULL,
                description TEXT NULL,
                expires_at TEXT NULL,
                last_used_at TEXT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT NULL,
                server_version INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(telegram_user_id) ON DELETE CASCADE
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
                route_version INTEGER NULL,
                server_version INTEGER NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL UNIQUE,
                lang TEXT NULL,
                json_payload TEXT NULL,
                insights_json TEXT NULL,
                version INTEGER NULL,
                server_version INTEGER NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_favorited INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL,
                updated_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
            );
            "#,
        )
        .expect("create schema");
}

fn test_config(
    label: &str,
    allowed_user_ids: HashSet<i64>,
    redis_enabled: bool,
    redis_required: bool,
) -> ApiRuntimeConfig {
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
            "com.example.app".to_string(),
            "test-client".to_string(),
            "ios.app".to_string(),
            "webapp".to_string(),
        ]),
        api_rate_limit_window_seconds: 60,
        api_rate_limit_cooldown_multiplier: 2.0,
        api_rate_limit_default: 100,
        api_rate_limit_summaries: 200,
        api_rate_limit_requests: 10,
        api_rate_limit_search: 50,
        redis_enabled,
        redis_required,
        redis_url: if redis_enabled {
            Some("redis://127.0.0.1:1/0".to_string())
        } else {
            None
        },
        redis_host: "127.0.0.1".to_string(),
        redis_port: 6379,
        redis_db: 0,
        redis_password: Some("password".to_string()),
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

fn now_rfc3339() -> String {
    Utc::now().to_rfc3339()
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
                is_owner,
                Utc::now().timestamp_millis(),
                now
            ],
        )
        .expect("insert user");
}

fn insert_request_with_summary(
    path: &Path,
    user_id: i64,
    normalized_url: &str,
    lang: &str,
    is_read: bool,
    json_payload: &str,
) {
    let connection = Connection::open(path).expect("open sqlite");
    let now = now_rfc3339();
    connection
        .execute(
            r#"
            INSERT INTO requests (
                created_at, updated_at, type, status, user_id, normalized_url, route_version, server_version, is_deleted
            ) VALUES (?1, ?1, 'url', 'completed', ?2, ?3, 1, ?4, 0)
            "#,
            params![now, user_id, normalized_url, Utc::now().timestamp_millis()],
        )
        .expect("insert request");
    let request_id = connection.last_insert_rowid();
    connection
        .execute(
            r#"
            INSERT INTO summaries (
                request_id, lang, json_payload, version, server_version, is_read, is_deleted, updated_at, created_at
            ) VALUES (?1, ?2, ?3, 1, ?4, ?5, 0, ?6, ?6)
            "#,
            params![
                request_id,
                lang,
                json_payload,
                Utc::now().timestamp_millis(),
                is_read,
                now
            ],
        )
        .expect("insert summary");
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

fn encode_telegram_auth_hash(
    bot_token: &str,
    user_id: i64,
    auth_date: i64,
    username: Option<&str>,
    first_name: Option<&str>,
    last_name: Option<&str>,
    photo_url: Option<&str>,
) -> String {
    let mut data_check = vec![format!("auth_date={auth_date}"), format!("id={user_id}")];
    if let Some(value) = first_name.filter(|value| !value.is_empty()) {
        data_check.push(format!("first_name={value}"));
    }
    if let Some(value) = last_name.filter(|value| !value.is_empty()) {
        data_check.push(format!("last_name={value}"));
    }
    if let Some(value) = photo_url.filter(|value| !value.is_empty()) {
        data_check.push(format!("photo_url={value}"));
    }
    if let Some(value) = username.filter(|value| !value.is_empty()) {
        data_check.push(format!("username={value}"));
    }
    data_check.sort();

    let secret_key = Sha256::digest(bot_token.as_bytes());
    let mut mac = HmacSha256::new_from_slice(secret_key.as_slice()).expect("telegram hmac");
    mac.update(data_check.join("\n").as_bytes());
    hex_string(&mac.finalize().into_bytes())
}

fn encode_webapp_init_data(
    bot_token: &str,
    user_id: i64,
    username: &str,
    auth_date: i64,
) -> String {
    let user_payload = json!({
        "id": user_id,
        "username": username,
        "first_name": "Web",
    })
    .to_string();
    let mut pairs = vec![
        ("auth_date".to_string(), auth_date.to_string()),
        ("query_id".to_string(), "AAHb-test".to_string()),
        ("user".to_string(), user_payload),
    ];
    pairs.sort_by(|left, right| left.0.cmp(&right.0));
    let data_check = pairs
        .iter()
        .map(|(key, value)| format!("{key}={value}"))
        .collect::<Vec<_>>()
        .join("\n");

    let mut secret = HmacSha256::new_from_slice(b"WebAppData").expect("webapp secret");
    secret.update(bot_token.as_bytes());
    let secret_key = secret.finalize().into_bytes();

    let mut mac = HmacSha256::new_from_slice(&secret_key).expect("webapp hmac");
    mac.update(data_check.as_bytes());
    let hash = hex_string(&mac.finalize().into_bytes());

    let mut serializer = form_urlencoded::Serializer::new(String::new());
    for (key, value) in pairs {
        serializer.append_pair(&key, &value);
    }
    serializer.append_pair("hash", &hash);
    serializer.finish()
}

fn derive_user_id_from_sub(provider: &str, sub: &str) -> i64 {
    let digest = Sha256::digest(format!("{provider}:{sub}").as_bytes());
    let modulus = 1_000_000_000_000_000u64;
    let mut acc = 0u64;
    for byte in digest {
        acc = ((acc * 256) + byte as u64) % modulus;
    }
    acc as i64
}

#[derive(Serialize)]
struct OAuthTokenClaims<'a> {
    sub: &'a str,
    email: &'a str,
    name: &'a str,
    email_verified: bool,
    aud: &'a str,
    iss: &'a str,
    exp: usize,
    iat: usize,
}

fn encode_oauth_token(client_id: &str, issuer: &str, sub: &str, email: &str, name: &str) -> String {
    let now = Utc::now().timestamp() as usize;
    let mut header = Header::new(Algorithm::RS256);
    header.kid = Some(TEST_OAUTH_KID.to_string());
    jsonwebtoken::encode(
        &header,
        &OAuthTokenClaims {
            sub,
            email,
            name,
            email_verified: true,
            aud: client_id,
            iss: issuer,
            exp: now + 300,
            iat: now,
        },
        &EncodingKey::from_rsa_pem(TEST_OAUTH_PRIVATE_KEY.as_bytes()).expect("rsa key"),
    )
    .expect("encode oauth token")
}

async fn spawn_jwks_server() -> (String, JoinHandle<()>) {
    let payload = Arc::new(json!({
        "keys": [{
            "kty": "RSA",
            "use": "sig",
            "kid": TEST_OAUTH_KID,
            "alg": "RS256",
            "n": TEST_OAUTH_JWK_N,
            "e": TEST_OAUTH_JWK_E,
        }]
    }));
    let app = Router::new().route(
        "/jwks",
        get({
            let payload = payload.clone();
            move || {
                let payload = payload.clone();
                async move { Json((*payload).clone()) }
            }
        }),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind jwks");
    let address = listener.local_addr().expect("jwks addr");
    let handle = tokio::spawn(async move {
        axum::serve(listener, app).await.expect("jwks server");
    });
    (format!("http://{address}/jwks"), handle)
}

fn hex_string(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[tokio::test]
async fn telegram_login_refresh_logout_and_sessions_flow() {
    let config = test_config("telegram-auth", HashSet::from([123456789]), false, false);
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    let bot_token = config.bot_token.clone().expect("bot token");
    let app = build_test_app(config).await;

    let auth_date = Utc::now().timestamp();
    let login_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/telegram-login",
        &[],
        Some(json!({
            "id": 123456789,
            "hash": encode_telegram_auth_hash(
                &bot_token,
                123456789,
                auth_date,
                Some("testuser"),
                Some("Test"),
                None,
                None,
            ),
            "auth_date": auth_date,
            "username": "testuser",
            "first_name": "Test",
            "client_id": "com.example.app",
        })),
    )
    .await;
    assert_eq!(login_response.status(), StatusCode::OK);
    let login_json = read_json(login_response).await;
    let refresh_token = login_json["data"]["tokens"]["refreshToken"]
        .as_str()
        .expect("refresh token")
        .to_string();
    let access_token = login_json["data"]["tokens"]["accessToken"]
        .as_str()
        .expect("access token")
        .to_string();
    assert!(login_json["data"]["sessionId"].as_i64().unwrap_or_default() > 0);

    let refresh_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/refresh",
        &[],
        Some(json!({"refresh_token": refresh_token})),
    )
    .await;
    assert_eq!(refresh_response.status(), StatusCode::OK);
    let refresh_json = read_json(refresh_response).await;
    assert!(
        refresh_json["data"]["tokens"]["accessToken"]
            .as_str()
            .expect("new access")
            .len()
            > 16
    );
    assert!(refresh_json["data"]["tokens"]["refreshToken"].is_null());

    let sessions_response = send_request(
        &app,
        Method::GET,
        "/v1/auth/sessions",
        &[("authorization", format!("Bearer {access_token}"))],
        None,
    )
    .await;
    assert_eq!(sessions_response.status(), StatusCode::OK);
    let sessions_json = read_json(sessions_response).await;
    assert_eq!(
        sessions_json["data"]["sessions"].as_array().unwrap().len(),
        1
    );
    assert_eq!(
        sessions_json["data"]["sessions"][0]["clientId"].as_str(),
        Some("com.example.app")
    );

    let logout_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/logout",
        &[("authorization", format!("Bearer {access_token}"))],
        Some(json!({"refresh_token": refresh_token})),
    )
    .await;
    assert_eq!(logout_response.status(), StatusCode::OK);
    let logout_json = read_json(logout_response).await;
    assert_eq!(
        logout_json["data"]["message"].as_str(),
        Some("Logged out successfully")
    );

    let connection = Connection::open(db_path).expect("open sqlite");
    let revoked: i64 = connection
        .query_row("SELECT is_revoked FROM refresh_tokens LIMIT 1", [], |row| {
            row.get(0)
        })
        .expect("revoked flag");
    assert_eq!(revoked, 1);
    let _ = secret;
}

#[tokio::test]
async fn oauth_login_accepts_signed_jwks_tokens() {
    let apple_sub = "apple-user-subject";
    let google_sub = "google-user-subject";
    let apple_user_id = derive_user_id_from_sub("apple", apple_sub);
    let google_user_id = derive_user_id_from_sub("google", google_sub);

    let (jwks_url, handle) = spawn_jwks_server().await;
    let mut config = test_config(
        "oauth-login",
        HashSet::from([apple_user_id, google_user_id]),
        false,
        false,
    );
    let db_path = config.db_path.clone();
    config.apple_jwks_url = jwks_url.clone();
    config.google_jwks_url = jwks_url.clone();
    let app = build_test_app(config).await;

    let apple_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/apple-login",
        &[],
        Some(json!({
            "id_token": encode_oauth_token(
                "com.example.app",
                "https://appleid.apple.com",
                apple_sub,
                "apple@example.com",
                "Apple User",
            ),
            "client_id": "com.example.app",
            "given_name": "Apple",
            "family_name": "User",
        })),
    )
    .await;
    assert_eq!(apple_response.status(), StatusCode::OK);

    let google_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/google-login",
        &[],
        Some(json!({
            "id_token": encode_oauth_token(
                "com.example.app",
                "https://accounts.google.com",
                google_sub,
                "google@example.com",
                "Google User",
            ),
            "client_id": "com.example.app",
        })),
    )
    .await;
    assert_eq!(google_response.status(), StatusCode::OK);

    let connection = Connection::open(db_path).expect("open sqlite");
    let users: Vec<(i64, String)> = {
        let mut statement = connection
            .prepare("SELECT telegram_user_id, COALESCE(username, '') FROM users ORDER BY telegram_user_id")
            .expect("prepare users");
        let rows = statement
            .query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
            .expect("query users");
        rows.map(|row| row.expect("user row")).collect()
    };
    assert!(users
        .iter()
        .any(|(id, username)| *id == apple_user_id && username == "Apple User"));
    assert!(users
        .iter()
        .any(|(id, username)| *id == google_user_id && username == "Google User"));
    handle.abort();
}

#[tokio::test]
async fn secret_key_create_login_list_and_revoke_flow() {
    let config = test_config("secret-login", HashSet::from([42, 777]), false, false);
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, 42, "owner", true);
    let app = build_test_app(config).await;
    let owner_token = encode_access_jwt(&secret, 42, "owner", "com.example.app");

    let create_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/secret-keys",
        &[("authorization", format!("Bearer {owner_token}"))],
        Some(json!({
            "user_id": 777,
            "username": "target-user",
            "client_id": "ios.app",
            "label": "ios-key",
        })),
    )
    .await;
    assert_eq!(create_response.status(), StatusCode::OK);
    let create_json = read_json(create_response).await;
    let issued_secret = create_json["data"]["secret"]
        .as_str()
        .expect("issued secret")
        .to_string();
    let key_id = create_json["data"]["key"]["id"].as_i64().expect("key id");

    let login_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/secret-login",
        &[],
        Some(json!({
            "user_id": 777,
            "client_id": "ios.app",
            "secret": issued_secret,
        })),
    )
    .await;
    assert_eq!(login_response.status(), StatusCode::OK);
    let login_json = read_json(login_response).await;
    assert!(
        login_json["data"]["tokens"]["refreshToken"]
            .as_str()
            .expect("refresh token")
            .len()
            > 16
    );

    let list_response = send_request(
        &app,
        Method::GET,
        "/v1/auth/secret-keys?user_id=777",
        &[("authorization", format!("Bearer {owner_token}"))],
        None,
    )
    .await;
    assert_eq!(list_response.status(), StatusCode::OK);
    let list_json = read_json(list_response).await;
    assert_eq!(list_json["data"]["keys"].as_array().unwrap().len(), 1);

    let revoke_response = send_request(
        &app,
        Method::POST,
        &format!("/v1/auth/secret-keys/{key_id}/revoke"),
        &[("authorization", format!("Bearer {owner_token}"))],
        Some(json!({"reason": "test"})),
    )
    .await;
    assert_eq!(revoke_response.status(), StatusCode::OK);
    let revoke_json = read_json(revoke_response).await;
    assert_eq!(
        revoke_json["data"]["key"]["status"].as_str(),
        Some("revoked")
    );
}

#[tokio::test]
async fn telegram_link_flow_round_trips_status() {
    let config = test_config(
        "telegram-link",
        HashSet::from([123456789, 987654321]),
        false,
        false,
    );
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    let bot_token = config.bot_token.clone().expect("bot token");
    seed_user(&db_path, 123456789, "link-user", false);
    let app = build_test_app(config).await;
    let access_token = encode_access_jwt(&secret, 123456789, "link-user", "com.example.app");

    let begin_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/me/telegram/link",
        &[("authorization", format!("Bearer {access_token}"))],
        None,
    )
    .await;
    assert_eq!(begin_response.status(), StatusCode::OK);
    let begin_json = read_json(begin_response).await;
    let nonce = begin_json["data"]["nonce"]
        .as_str()
        .expect("nonce")
        .to_string();

    let auth_date = Utc::now().timestamp();
    let complete_response = send_request(
        &app,
        Method::POST,
        "/v1/auth/me/telegram/complete",
        &[("authorization", format!("Bearer {access_token}"))],
        Some(json!({
            "id": 987654321,
            "hash": encode_telegram_auth_hash(
                &bot_token,
                987654321,
                auth_date,
                Some("linked"),
                Some("Linked"),
                Some("User"),
                None,
            ),
            "auth_date": auth_date,
            "username": "linked",
            "first_name": "Linked",
            "last_name": "User",
            "client_id": "com.example.app",
            "nonce": nonce,
        })),
    )
    .await;
    assert_eq!(complete_response.status(), StatusCode::OK);
    let complete_json = read_json(complete_response).await;
    assert_eq!(complete_json["data"]["linked"].as_bool(), Some(true));
    assert_eq!(
        complete_json["data"]["telegram_user_id"].as_i64(),
        Some(987654321)
    );

    let status_response = send_request(
        &app,
        Method::GET,
        "/v1/auth/me/telegram",
        &[("authorization", format!("Bearer {access_token}"))],
        None,
    )
    .await;
    assert_eq!(status_response.status(), StatusCode::OK);
    let status_json = read_json(status_response).await;
    assert_eq!(status_json["data"]["username"].as_str(), Some("linked"));
}

#[tokio::test]
async fn user_preferences_and_stats_routes_match_expected_shapes() {
    let config = test_config("user-routes", HashSet::from([123456789]), false, false);
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, 123456789, "stats-user", false);
    insert_request_with_summary(
        &db_path,
        123456789,
        "https://example.com/story",
        "en",
        false,
        r#"{"estimated_reading_time_min":5,"topic_tags":["Rust","AI"],"metadata":{"domain":"example.com"}}"#,
    );
    insert_request_with_summary(
        &db_path,
        123456789,
        "https://example.org/legacy",
        "ru",
        true,
        r#"{"estimated_reading_time_min":3,"topic_tags":["Legacy"],"metadata":{"domain":"example.org"}}"#,
    );
    insert_request_with_summary(
        &db_path,
        123456789,
        "https://example.net/bad",
        "en",
        true,
        "not-json",
    );
    let app = build_test_app(config).await;
    let access_token = encode_access_jwt(&secret, 123456789, "stats-user", "com.example.app");

    let pref_response = send_request(
        &app,
        Method::GET,
        "/v1/user/preferences",
        &[("authorization", format!("Bearer {access_token}"))],
        None,
    )
    .await;
    assert_eq!(pref_response.status(), StatusCode::OK);
    let pref_json = read_json(pref_response).await;
    assert_eq!(pref_json["data"]["langPreference"].as_str(), Some("en"));

    let patch_response = send_request(
        &app,
        Method::PATCH,
        "/v1/user/preferences",
        &[("authorization", format!("Bearer {access_token}"))],
        Some(json!({
            "lang_preference": "ru",
            "notification_settings": {"enabled": false, "frequency": "weekly"},
        })),
    )
    .await;
    assert_eq!(patch_response.status(), StatusCode::OK);
    let patch_json = read_json(patch_response).await;
    assert!(patch_json["data"]["updatedFields"]
        .as_array()
        .unwrap()
        .iter()
        .any(|field| field.as_str() == Some("lang_preference")));

    let stats_response = send_request(
        &app,
        Method::GET,
        "/v1/user/stats",
        &[("authorization", format!("Bearer {access_token}"))],
        None,
    )
    .await;
    assert_eq!(stats_response.status(), StatusCode::OK);
    let stats_json = read_json(stats_response).await;
    assert_eq!(stats_json["data"]["totalSummaries"].as_i64(), Some(3));
    assert_eq!(stats_json["data"]["unreadCount"].as_i64(), Some(1));
    assert_eq!(stats_json["data"]["totalReadingTimeMin"].as_i64(), Some(8));
    assert_eq!(
        stats_json["data"]["languageDistribution"]["en"].as_i64(),
        Some(2)
    );
    assert_eq!(
        stats_json["data"]["languageDistribution"]["ru"].as_i64(),
        Some(1)
    );
    assert_eq!(
        stats_json["data"]["favoriteDomains"][0]["domain"].as_str(),
        Some("example.com")
    );
}

#[tokio::test]
async fn system_routes_enforce_owner_and_support_db_dump_range() {
    let config = test_config("system-routes", HashSet::from([42, 99]), false, false);
    let db_path = config.db_path.clone();
    let secret = config.jwt_secret_key.clone().expect("jwt secret");
    seed_user(&db_path, 42, "owner", true);
    seed_user(&db_path, 99, "member", false);
    let app = build_test_app(config).await;
    let owner_token = encode_access_jwt(&secret, 42, "owner", "com.example.app");
    let member_token = encode_access_jwt(&secret, 99, "member", "com.example.app");

    let forbidden = send_request(
        &app,
        Method::GET,
        "/v1/system/db-info",
        &[("authorization", format!("Bearer {member_token}"))],
        None,
    )
    .await;
    assert_eq!(forbidden.status(), StatusCode::FORBIDDEN);

    let info = send_request(
        &app,
        Method::GET,
        "/v1/system/db-info",
        &[("authorization", format!("Bearer {owner_token}"))],
        None,
    )
    .await;
    assert_eq!(info.status(), StatusCode::OK);
    let info_json = read_json(info).await;
    assert!(
        info_json["data"]["table_counts"]["users"]
            .as_i64()
            .unwrap_or_default()
            >= 2
    );

    let clear = send_request(
        &app,
        Method::POST,
        "/v1/system/clear-cache",
        &[("authorization", format!("Bearer {owner_token}"))],
        None,
    )
    .await;
    assert_eq!(clear.status(), StatusCode::OK);
    let clear_json = read_json(clear).await;
    assert_eq!(clear_json["data"]["cleared_keys"].as_i64(), Some(0));

    let head = send_request(
        &app,
        Method::HEAD,
        "/v1/system/db-dump",
        &[("authorization", format!("Bearer {owner_token}"))],
        None,
    )
    .await;
    assert_eq!(head.status(), StatusCode::OK);
    let etag = head
        .headers()
        .get("etag")
        .and_then(|value| value.to_str().ok())
        .expect("etag")
        .to_string();
    assert_eq!(
        head.headers()
            .get("accept-ranges")
            .and_then(|value| value.to_str().ok()),
        Some("bytes")
    );

    let dump = send_request(
        &app,
        Method::GET,
        "/v1/system/db-dump",
        &[("authorization", format!("Bearer {owner_token}"))],
        None,
    )
    .await;
    assert_eq!(dump.status(), StatusCode::OK);
    assert_eq!(
        dump.headers()
            .get("etag")
            .and_then(|value| value.to_str().ok()),
        Some(etag.as_str())
    );

    let ranged = send_request(
        &app,
        Method::GET,
        "/v1/system/db-dump",
        &[
            ("authorization", format!("Bearer {owner_token}")),
            ("range", "bytes=0-9".to_string()),
        ],
        None,
    )
    .await;
    assert_eq!(ranged.status(), StatusCode::PARTIAL_CONTENT);
    assert_eq!(
        ranged
            .headers()
            .get("content-range")
            .and_then(|value| value.to_str().ok())
            .map(|value| value.starts_with("bytes 0-9/")),
        Some(true)
    );
}

#[tokio::test]
async fn rate_limit_actor_uses_webapp_then_host_fallbacks() {
    let mut config = test_config("rate-limit", HashSet::from([4242]), false, false);
    config.api_rate_limit_default = 1;
    let bot_token = config.bot_token.clone().expect("bot token");
    let app = build_test_app(config).await;

    let first = send_request(
        &app,
        Method::GET,
        "/health",
        &[("x-forwarded-for", "10.0.0.1".to_string())],
        None,
    )
    .await;
    assert_eq!(first.status(), StatusCode::OK);

    let second = send_request(
        &app,
        Method::GET,
        "/health",
        &[("x-forwarded-for", "10.0.0.1".to_string())],
        None,
    )
    .await;
    assert_eq!(second.status(), StatusCode::TOO_MANY_REQUESTS);

    let third = send_request(
        &app,
        Method::GET,
        "/health",
        &[("x-forwarded-for", "10.0.0.2".to_string())],
        None,
    )
    .await;
    assert_eq!(third.status(), StatusCode::OK);

    let init_data = encode_webapp_init_data(&bot_token, 4242, "web-user", Utc::now().timestamp());
    let webapp_first = send_request(
        &app,
        Method::GET,
        "/v1/user/preferences",
        &[("x-telegram-init-data", init_data.clone())],
        None,
    )
    .await;
    assert_eq!(webapp_first.status(), StatusCode::OK);

    let webapp_second = send_request(
        &app,
        Method::GET,
        "/v1/user/preferences",
        &[("x-telegram-init-data", init_data)],
        None,
    )
    .await;
    assert_eq!(webapp_second.status(), StatusCode::TOO_MANY_REQUESTS);
}

#[tokio::test]
async fn redis_required_rate_limit_backend_fails_closed() {
    let config = test_config("redis-required", HashSet::new(), true, true);
    let app = build_test_app(config).await;

    let response = send_request(&app, Method::GET, "/health", &[], None).await;
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    let headers = response.headers().clone();
    let body = read_json(response).await;
    assert_eq!(
        body["error"]["code"].as_str(),
        Some("RATE_LIMIT_BACKEND_UNAVAILABLE")
    );
    assert_eq!(
        headers
            .get("x-correlation-id")
            .and_then(|value| value.to_str().ok())
            .map(|value| !value.is_empty()),
        Some(true)
    );
}
