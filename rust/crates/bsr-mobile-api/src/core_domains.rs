use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::extract::rejection::{JsonRejection, QueryRejection};
use axum::extract::{FromRef, FromRequestParts, Path, Query, State};
use axum::http::header::{
    ACCEPT_RANGES, CONTENT_DISPOSITION, CONTENT_LENGTH, CONTENT_RANGE, CONTENT_TYPE, ETAG, RANGE,
};
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Extension, Json, Router};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use bsr_persistence::{
    allowlisted_table_counts, complete_telegram_link, create_client_secret, create_refresh_token,
    delete_user, get_client_secret, get_client_secret_by_id, get_or_create_user,
    get_refresh_token_by_hash, get_user_by_telegram_id, increment_failed_attempts,
    list_active_sessions, list_client_secrets, list_user_summary_rows, mark_client_secret_revoked,
    normalize_datetime_text, open_connection, reset_failed_attempts, revoke_active_secrets,
    revoke_refresh_token, rotate_client_secret, set_client_secret_status, set_link_nonce,
    touch_client_secret_after_success, unlink_telegram, update_refresh_token_last_used,
    update_user_preferences, ClientSecretRecord, UserRecord,
};
use chrono::{DateTime, Duration, Utc};
use hmac::{Hmac, Mac};
use jsonwebtoken::{
    decode, decode_header, Algorithm, DecodingKey, EncodingKey, Header, Validation,
};
use rand::RngCore;
use redis::AsyncCommands;
use reqwest::Client;
use rusqlite::backup::Backup;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use tokio::fs;
use url::Url;

use crate::{
    error_json_response, success_json_response, ApiRuntimeConfig, AppState, AuthSource,
    AuthenticatedUser, CorrelationId,
};

type HmacSha256 = Hmac<Sha256>;

const ACCESS_TOKEN_EXPIRE_MINUTES: i64 = 60;
const REFRESH_TOKEN_EXPIRE_DAYS: i64 = 30;
const APPLE_ISSUER: &str = "https://appleid.apple.com";
const GOOGLE_ISSUERS: [&str; 2] = ["https://accounts.google.com", "accounts.google.com"];
const DB_DUMP_CACHE_STALE_SECONDS: i64 = 60;
const BACKUP_FILENAME: &str = "bite_size_reader_backup.sqlite";

#[derive(Debug, Clone)]
pub(crate) struct CurrentUser(pub AuthenticatedUser);

#[derive(Debug, Clone)]
pub(crate) struct OwnerUser {
    pub auth: AuthenticatedUser,
}

#[derive(Debug, Clone)]
pub(crate) struct AuthResolutionError(pub String);

#[derive(Debug, Deserialize)]
struct TelegramLoginRequest {
    #[serde(alias = "id")]
    telegram_user_id: i64,
    #[serde(alias = "hash")]
    auth_hash: String,
    auth_date: i64,
    username: Option<String>,
    first_name: Option<String>,
    last_name: Option<String>,
    photo_url: Option<String>,
    client_id: String,
}

#[derive(Debug, Deserialize)]
struct RefreshTokenRequest {
    refresh_token: String,
}

#[derive(Debug, Deserialize)]
struct AppleLoginRequest {
    id_token: String,
    client_id: String,
    #[serde(rename = "authorization_code")]
    _authorization_code: Option<String>,
    given_name: Option<String>,
    family_name: Option<String>,
}

#[derive(Debug, Deserialize)]
struct GoogleLoginRequest {
    id_token: String,
    client_id: String,
}

#[derive(Debug, Deserialize)]
struct SecretLoginRequest {
    user_id: i64,
    client_id: String,
    secret: String,
    #[serde(rename = "username")]
    _username: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SecretKeyCreateRequest {
    user_id: i64,
    client_id: String,
    label: Option<String>,
    description: Option<String>,
    expires_at: Option<String>,
    secret: Option<String>,
    username: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SecretKeyRotateRequest {
    label: Option<String>,
    description: Option<String>,
    expires_at: Option<String>,
    secret: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SecretKeyRevokeRequest {
    reason: Option<String>,
}

#[derive(Debug, Deserialize)]
struct TelegramLinkCompleteRequest {
    #[serde(alias = "id")]
    telegram_user_id: i64,
    #[serde(alias = "hash")]
    auth_hash: String,
    auth_date: i64,
    username: Option<String>,
    first_name: Option<String>,
    last_name: Option<String>,
    photo_url: Option<String>,
    #[serde(rename = "client_id")]
    _client_id: String,
    nonce: String,
}

#[derive(Debug, Deserialize)]
struct UpdatePreferencesRequest {
    lang_preference: Option<String>,
    notification_settings: Option<Map<String, Value>>,
    app_settings: Option<Map<String, Value>>,
}

#[derive(Debug, Deserialize)]
struct SecretKeyListQuery {
    user_id: Option<i64>,
    client_id: Option<String>,
    status: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OAuthClaims {
    sub: Option<String>,
    email: Option<String>,
    name: Option<String>,
    #[serde(default)]
    _email_verified: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct AccessTokenClaims {
    user_id: i64,
    username: Option<String>,
    client_id: Option<String>,
    exp: i64,
    #[serde(rename = "type")]
    token_type: String,
    iat: i64,
}

#[derive(Debug, Deserialize, Serialize)]
struct RefreshTokenClaims {
    user_id: i64,
    client_id: Option<String>,
    exp: i64,
    #[serde(rename = "type")]
    token_type: String,
    iat: i64,
}

#[derive(Debug, Deserialize)]
struct JwksDocument {
    keys: Vec<JwkKey>,
}

#[derive(Debug, Deserialize)]
struct JwkKey {
    kid: Option<String>,
    kty: Option<String>,
    #[serde(rename = "alg")]
    _alg: Option<String>,
    #[serde(rename = "use")]
    use_: Option<String>,
    n: Option<String>,
    e: Option<String>,
}

#[derive(Debug)]
struct DbDumpFile {
    path: PathBuf,
    filename: String,
    etag: String,
    len: u64,
}

impl<S> FromRequestParts<S> for CurrentUser
where
    AppState: axum::extract::FromRef<S>,
    S: Send + Sync,
{
    type Rejection = Response;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        state: &S,
    ) -> Result<Self, Self::Rejection> {
        let app_state = AppState::from_ref(state);
        let correlation_id = parts
            .extensions
            .get::<CorrelationId>()
            .map(|value| value.0.clone())
            .unwrap_or_default();

        if let Some(user) = parts.extensions.get::<AuthenticatedUser>().cloned() {
            if matches!(user.auth_source, AuthSource::Jwt) {
                if let Err(response) = validate_current_user_contract(
                    &user,
                    correlation_id.clone(),
                    &app_state.runtime.config,
                ) {
                    return Err(response);
                }
            }
            return Ok(Self(user));
        }

        if let Some(error) = parts.extensions.get::<AuthResolutionError>() {
            return Err(authentication_invalid_response(
                &correlation_id,
                &app_state.runtime.config,
                &error.0,
            ));
        }

        Err(authentication_required_response(
            &correlation_id,
            &app_state.runtime.config,
        ))
    }
}

impl<S> FromRequestParts<S> for OwnerUser
where
    AppState: axum::extract::FromRef<S>,
    S: Send + Sync,
{
    type Rejection = Response;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        state: &S,
    ) -> Result<Self, Self::Rejection> {
        let app_state = AppState::from_ref(state);
        let correlation_id = parts
            .extensions
            .get::<CorrelationId>()
            .map(|value| value.0.clone())
            .unwrap_or_default();
        let CurrentUser(auth) = CurrentUser::from_request_parts(parts, state).await?;
        let connection = open_connection(&app_state.runtime.config.db_path).map_err(|err| {
            internal_error_response(
                &correlation_id,
                &app_state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            )
        })?;
        let Some(record) = get_user_by_telegram_id(&connection, auth.user_id).map_err(|err| {
            internal_error_response(
                &correlation_id,
                &app_state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            )
        })?
        else {
            return Err(forbidden_response(
                &correlation_id,
                &app_state.runtime.config,
                "Owner permissions required",
                "FORBIDDEN",
            ));
        };
        if !record.is_owner {
            return Err(forbidden_response(
                &correlation_id,
                &app_state.runtime.config,
                "Owner permissions required",
                "FORBIDDEN",
            ));
        }
        Ok(Self { auth })
    }
}

pub(crate) fn build_router() -> Router<AppState> {
    Router::new()
        .route("/v1/auth/telegram-login", post(telegram_login_handler))
        .route("/v1/auth/refresh", post(refresh_access_token_handler))
        .route("/v1/auth/logout", post(logout_handler))
        .route("/v1/auth/sessions", get(list_sessions_handler))
        .route(
            "/v1/auth/me",
            get(get_current_user_info_handler).delete(delete_account_handler),
        )
        .route("/v1/auth/apple-login", post(apple_login_handler))
        .route("/v1/auth/google-login", post(google_login_handler))
        .route("/v1/auth/secret-login", post(secret_login_handler))
        .route(
            "/v1/auth/secret-keys",
            post(create_secret_key_handler).get(list_secret_keys_handler),
        )
        .route(
            "/v1/auth/secret-keys/{key_id}/rotate",
            post(rotate_secret_key_handler),
        )
        .route(
            "/v1/auth/secret-keys/{key_id}/revoke",
            post(revoke_secret_key_handler),
        )
        .route(
            "/v1/auth/me/telegram",
            get(get_telegram_link_status_handler).delete(unlink_telegram_handler),
        )
        .route(
            "/v1/auth/me/telegram/link",
            post(begin_telegram_link_handler),
        )
        .route(
            "/v1/auth/me/telegram/complete",
            post(complete_telegram_link_handler),
        )
        .route(
            "/v1/user/preferences",
            get(get_user_preferences_handler).patch(update_user_preferences_handler),
        )
        .route("/v1/user/stats", get(get_user_stats_handler))
        .route("/v1/system/db-info", get(get_db_info_handler))
        .route("/v1/system/clear-cache", post(clear_cache_handler))
        .route(
            "/v1/system/db-dump",
            get(download_database_handler).head(head_database_handler),
        )
}

pub(crate) fn implemented_route_map() -> BTreeMap<&'static str, BTreeSet<String>> {
    let mut routes = BTreeMap::new();
    routes.insert("/v1/auth/telegram-login", set_of(["POST"]));
    routes.insert("/v1/auth/refresh", set_of(["POST"]));
    routes.insert("/v1/auth/logout", set_of(["POST"]));
    routes.insert("/v1/auth/sessions", set_of(["GET"]));
    routes.insert("/v1/auth/me", set_of(["GET", "DELETE"]));
    routes.insert("/v1/auth/apple-login", set_of(["POST"]));
    routes.insert("/v1/auth/google-login", set_of(["POST"]));
    routes.insert("/v1/auth/secret-login", set_of(["POST"]));
    routes.insert("/v1/auth/secret-keys", set_of(["GET", "POST"]));
    routes.insert("/v1/auth/secret-keys/{key_id}/rotate", set_of(["POST"]));
    routes.insert("/v1/auth/secret-keys/{key_id}/revoke", set_of(["POST"]));
    routes.insert("/v1/auth/me/telegram", set_of(["GET", "DELETE"]));
    routes.insert("/v1/auth/me/telegram/link", set_of(["POST"]));
    routes.insert("/v1/auth/me/telegram/complete", set_of(["POST"]));
    routes.insert("/v1/user/preferences", set_of(["GET", "PATCH"]));
    routes.insert("/v1/user/stats", set_of(["GET"]));
    routes.insert("/v1/system/db-info", set_of(["GET"]));
    routes.insert("/v1/system/clear-cache", set_of(["POST"]));
    routes.insert("/v1/system/db-dump", set_of(["GET", "HEAD"]));
    routes
}

async fn telegram_login_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    payload: Result<Json<TelegramLoginRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) =
        validate_client_id(&payload.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    if let Err(response) = verify_telegram_auth(
        payload.telegram_user_id,
        &payload.auth_hash,
        payload.auth_date,
        payload.username.as_deref(),
        payload.first_name.as_deref(),
        payload.last_name.as_deref(),
        payload.photo_url.as_deref(),
        &correlation_id.0,
        &state.runtime.config,
    ) {
        return response;
    }

    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let (user, _) = match get_or_create_user(
        &connection,
        payload.telegram_user_id,
        payload.username.as_deref(),
        false,
    ) {
        Ok(value) => value,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Authentication failed. Please try again.",
                "PROCESSING_ERROR",
                Some(json!({"reason": err.to_string()})),
                false,
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    let username = user.username.clone().or(payload.username.clone());
    let access_token = match create_access_token(
        payload.telegram_user_id,
        username.as_deref(),
        Some(payload.client_id.as_str()),
        &state.runtime.config,
    ) {
        Ok(token) => token,
        Err(response) => return response,
    };
    let (refresh_token, session_id) = match issue_refresh_token(
        &connection,
        payload.telegram_user_id,
        Some(payload.client_id.as_str()),
        None,
        None,
        &state.runtime.config,
        &correlation_id.0,
    ) {
        Ok(value) => value,
        Err(response) => return response,
    };

    success_json_response(
        json!({
            "tokens": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresIn": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "tokenType": "Bearer",
            },
            "sessionId": session_id,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn refresh_access_token_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    payload: Result<Json<RefreshTokenRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    let claims = match decode_refresh_token(
        &payload.refresh_token,
        &correlation_id.0,
        &state.runtime.config,
    ) {
        Ok(claims) => claims,
        Err(response) => return response,
    };
    if let Err(response) = validate_optional_client_id(
        claims.client_id.as_deref(),
        &correlation_id.0,
        &state.runtime.config,
    ) {
        return response;
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let token_hash = sha256_hex(payload.refresh_token.as_bytes());
    let Some(record) = (match get_refresh_token_by_hash(&connection, &token_hash) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "TOKEN_INVALID",
            "Invalid token: Refresh token is not recognized",
            Some(json!({"reason": "Refresh token is not recognized"})),
            false,
        );
    };
    if record.is_revoked {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "TOKEN_REVOKED",
            "Token has been revoked. Please re-authenticate.",
            None,
            false,
        );
    }
    let Some(user) = (match get_user_by_telegram_id(&connection, claims.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            "User with ID not found",
            json!({"resource_type": "User", "resource_id": claims.user_id.to_string()}),
        );
    };
    if let Err(err) = update_refresh_token_last_used(&connection, record.id) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    let access_token = match create_access_token(
        claims.user_id,
        user.username.as_deref(),
        claims.client_id.as_deref(),
        &state.runtime.config,
    ) {
        Ok(token) => token,
        Err(response) => return response,
    };

    success_json_response(
        json!({
            "tokens": {
                "accessToken": access_token,
                "refreshToken": Value::Null,
                "expiresIn": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "tokenType": "Bearer",
            }
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn logout_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    _user: CurrentUser,
    payload: Result<Json<RefreshTokenRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Ok(connection) = open_connection(&state.runtime.config.db_path) {
        let _ = revoke_refresh_token(&connection, &sha256_hex(payload.refresh_token.as_bytes()));
    }
    success_json_response(
        json!({"message": "Logged out successfully"}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn list_sessions_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(user): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let sessions = match list_active_sessions(&connection, user.user_id, &Utc::now().to_rfc3339()) {
        Ok(sessions) => sessions,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let payload = sessions
        .into_iter()
        .map(|session| {
            json!({
                "id": session.id,
                "clientId": session.client_id,
                "deviceInfo": session.device_info,
                "ipAddress": session.ip_address,
                "lastUsedAt": normalize_datetime_text(session.last_used_at.as_deref()),
                "createdAt": normalize_datetime_text(session.created_at.as_deref()).unwrap_or_default(),
                "isCurrent": false,
            })
        })
        .collect::<Vec<_>>();
    success_json_response(
        json!({"sessions": payload}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_current_user_info_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let (user, _) =
        match get_or_create_user(&connection, auth.user_id, auth.username.as_deref(), false) {
            Ok(value) => value,
            Err(err) => {
                return internal_error_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Database temporarily unavailable",
                    "DATABASE_ERROR",
                    Some(json!({"reason": err.to_string()})),
                    true,
                    StatusCode::SERVICE_UNAVAILABLE,
                );
            }
        };
    success_json_response(
        json!({
            "userId": auth.user_id,
            "username": auth.username.unwrap_or_default(),
            "clientId": auth.client_id,
            "isOwner": user.is_owner,
            "createdAt": normalize_datetime_text(user.created_at.as_deref()).unwrap_or_default(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn delete_account_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(_) = (match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("User with ID {} not found", auth.user_id),
            json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
        );
    };
    if let Err(err) = delete_user(&connection, auth.user_id) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Failed to delete account",
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    }
    success_json_response(
        json!({"success": true}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn apple_login_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    payload: Result<Json<AppleLoginRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) =
        validate_client_id(&payload.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let claims = match verify_oauth_id_token(
        &payload.id_token,
        &payload.client_id,
        &state.runtime.config.apple_jwks_url,
        &[APPLE_ISSUER],
        &correlation_id.0,
        &state.runtime.config,
        "Apple",
    )
    .await
    {
        Ok(claims) => claims,
        Err(response) => return response,
    };
    let Some(sub) = claims.sub else {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Apple ID token missing 'sub' claim",
            None,
            false,
        );
    };
    let derived_user_id = derive_user_id_from_sub("apple", &sub);
    if let Err(response) =
        ensure_allowed_oauth_user(derived_user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let display_name = match (payload.given_name, payload.family_name) {
        (Some(first), Some(last)) if !first.is_empty() || !last.is_empty() => {
            Some(format!("{first} {last}").trim().to_string())
        }
        (Some(first), None) if !first.is_empty() => Some(first),
        (None, Some(last)) if !last.is_empty() => Some(last),
        _ => None,
    };
    oauth_login_response(
        &state,
        &correlation_id.0,
        derived_user_id,
        display_name.or(claims.email).as_deref(),
        Some(payload.client_id.as_str()),
    )
    .await
}

async fn google_login_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    payload: Result<Json<GoogleLoginRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) =
        validate_client_id(&payload.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let claims = match verify_oauth_id_token(
        &payload.id_token,
        &payload.client_id,
        &state.runtime.config.google_jwks_url,
        &GOOGLE_ISSUERS,
        &correlation_id.0,
        &state.runtime.config,
        "Google",
    )
    .await
    {
        Ok(claims) => claims,
        Err(response) => return response,
    };
    let Some(sub) = claims.sub else {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Google ID token missing 'sub' claim",
            None,
            false,
        );
    };
    let derived_user_id = derive_user_id_from_sub("google", &sub);
    if let Err(response) =
        ensure_allowed_oauth_user(derived_user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    oauth_login_response(
        &state,
        &correlation_id.0,
        derived_user_id,
        claims.name.or(claims.email).as_deref(),
        Some(payload.client_id.as_str()),
    )
    .await
}

async fn oauth_login_response(
    state: &AppState,
    correlation_id: &str,
    user_id: i64,
    username: Option<&str>,
    client_id: Option<&str>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                correlation_id,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let (user, _) = match get_or_create_user(&connection, user_id, username, false) {
        Ok(value) => value,
        Err(err) => {
            return internal_error_response(
                correlation_id,
                &state.runtime.config,
                "Authentication failed. Please try again.",
                "PROCESSING_ERROR",
                Some(json!({"reason": err.to_string()})),
                false,
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    let access_token = match create_access_token(
        user_id,
        user.username.as_deref(),
        client_id,
        &state.runtime.config,
    ) {
        Ok(token) => token,
        Err(response) => return response,
    };
    let (refresh_token, session_id) = match issue_refresh_token(
        &connection,
        user_id,
        client_id,
        None,
        None,
        &state.runtime.config,
        correlation_id,
    ) {
        Ok(value) => value,
        Err(response) => return response,
    };
    success_json_response(
        json!({
            "tokens": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresIn": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "tokenType": "Bearer",
            },
            "sessionId": session_id,
        }),
        correlation_id.to_string(),
        &state.runtime.config,
    )
}

async fn secret_login_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    payload: Result<Json<SecretLoginRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) = ensure_secret_login_enabled(&correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(response) =
        validate_client_id(&payload.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    if let Err(response) =
        ensure_allowed_secret_user(payload.user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(user) = (match get_user_by_telegram_id(&connection, payload.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("User with ID {} not found", payload.user_id),
            json!({"resource_type": "User", "resource_id": payload.user_id.to_string()}),
        );
    };
    let Some(secret_record) =
        (match get_client_secret(&connection, payload.user_id, &payload.client_id) {
            Ok(record) => record,
            Err(err) => {
                return internal_error_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Database temporarily unavailable",
                    "DATABASE_ERROR",
                    Some(json!({"reason": err.to_string()})),
                    true,
                    StatusCode::SERVICE_UNAVAILABLE,
                );
            }
        })
    else {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid credentials",
            None,
            false,
        );
    };
    if secret_record.status == "revoked" {
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Secret has been revoked",
            None,
            false,
        );
    }
    let now = Utc::now();
    if secret_record.status == "locked" {
        if let Some(locked_until) = parse_datetime(secret_record.locked_until.as_deref()) {
            if locked_until < now {
                let _ = set_client_secret_status(&connection, secret_record.id, "active");
                let _ = reset_failed_attempts(&connection, secret_record.id);
            } else {
                return forbidden_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Secret is temporarily locked",
                    "FORBIDDEN",
                );
            }
        } else {
            return forbidden_response(
                &correlation_id.0,
                &state.runtime.config,
                "Secret is temporarily locked",
                "FORBIDDEN",
            );
        }
    }
    if let Some(expires_at) = parse_datetime(secret_record.expires_at.as_deref()) {
        if expires_at < now {
            let _ = set_client_secret_status(&connection, secret_record.id, "expired");
            return auth_error_response(
                &correlation_id.0,
                &state.runtime.config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                "Secret has expired",
                None,
                false,
            );
        }
    }
    let provided_secret = match validate_secret_value(
        &payload.secret,
        true,
        &correlation_id.0,
        &state.runtime.config,
    ) {
        Ok(secret) => secret,
        Err(response) => return response,
    };
    let expected_hash = hash_secret(
        &provided_secret,
        &secret_record.secret_salt,
        &state.runtime.config,
    );
    if expected_hash != secret_record.secret_hash {
        let _ = increment_failed_attempts(
            &connection,
            secret_record.id,
            state.runtime.config.secret_max_failed_attempts as i64,
            state.runtime.config.secret_lockout_minutes as i64,
        );
        return auth_error_response(
            &correlation_id.0,
            &state.runtime.config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid credentials",
            None,
            false,
        );
    }
    let _ = reset_failed_attempts(&connection, secret_record.id);
    let _ =
        touch_client_secret_after_success(&connection, secret_record.id, &Utc::now().to_rfc3339());
    let access_token = match create_access_token(
        payload.user_id,
        user.username.as_deref(),
        Some(payload.client_id.as_str()),
        &state.runtime.config,
    ) {
        Ok(token) => token,
        Err(response) => return response,
    };
    let (refresh_token, session_id) = match issue_refresh_token(
        &connection,
        payload.user_id,
        Some(payload.client_id.as_str()),
        None,
        None,
        &state.runtime.config,
        &correlation_id.0,
    ) {
        Ok(value) => value,
        Err(response) => return response,
    };
    success_json_response(
        json!({
            "tokens": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
                "expiresIn": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "tokenType": "Bearer",
            },
            "sessionId": session_id,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn create_secret_key_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
    payload: Result<Json<SecretKeyCreateRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) = ensure_secret_login_enabled(&correlation_id.0, &state.runtime.config) {
        return response;
    }
    if let Err(response) =
        validate_client_id(&payload.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    if let Err(response) =
        ensure_allowed_secret_user(payload.user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let (target_user, _) = match get_or_create_user(
        &connection,
        payload.user_id,
        payload.username.as_deref(),
        false,
    ) {
        Ok(value) => value,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let _ = revoke_active_secrets(
        &connection,
        target_user.telegram_user_id,
        &payload.client_id,
    );
    let secret_value = match payload.secret.as_deref() {
        Some(secret) => {
            match validate_secret_value(secret, false, &correlation_id.0, &state.runtime.config) {
                Ok(value) => value,
                Err(response) => return response,
            }
        }
        None => generate_secret_value(&state.runtime.config),
    };
    let salt = generate_hex_token(16);
    let secret_hash = hash_secret(&secret_value, &salt, &state.runtime.config);
    let expires_at = match coerce_datetime(
        payload.expires_at.as_deref(),
        &correlation_id.0,
        &state.runtime.config,
    ) {
        Ok(value) => value,
        Err(response) => return response,
    };
    let record = match create_client_secret(
        &connection,
        target_user.telegram_user_id,
        &payload.client_id,
        &secret_hash,
        &salt,
        "active",
        payload.label.as_deref(),
        payload.description.as_deref(),
        expires_at.as_deref(),
    ) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    success_json_response(
        json!({
            "secret": secret_value,
            "key": serialize_secret(&record),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn rotate_secret_key_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
    Path(key_id): Path<i64>,
    payload: Result<Json<SecretKeyRotateRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    if let Err(response) = ensure_secret_login_enabled(&correlation_id.0, &state.runtime.config) {
        return response;
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(record) = (match get_client_secret_by_id(&connection, key_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("Secret key with ID {} not found", key_id),
            json!({"resource_type": "Secret key", "resource_id": key_id.to_string()}),
        );
    };
    if let Err(response) =
        ensure_allowed_secret_user(record.user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    if let Err(response) =
        validate_client_id(&record.client_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    let secret_value = match payload.secret.as_deref() {
        Some(secret) => {
            match validate_secret_value(secret, false, &correlation_id.0, &state.runtime.config) {
                Ok(value) => value,
                Err(response) => return response,
            }
        }
        None => generate_secret_value(&state.runtime.config),
    };
    let salt = generate_hex_token(16);
    let secret_hash = hash_secret(&secret_value, &salt, &state.runtime.config);
    let expires_at_input = payload
        .expires_at
        .clone()
        .or_else(|| record.expires_at.clone());
    let expires_at = match expires_at_input {
        Some(value) => match coerce_datetime(
            Some(value.as_str()),
            &correlation_id.0,
            &state.runtime.config,
        ) {
            Ok(value) => value,
            Err(response) => return response,
        },
        None => None,
    };
    let label = payload.label.as_deref().or(record.label.as_deref());
    let description = payload
        .description
        .as_deref()
        .or(record.description.as_deref());
    if let Err(err) = rotate_client_secret(
        &connection,
        key_id,
        &secret_hash,
        &salt,
        label,
        description,
        expires_at.as_deref(),
    ) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    let updated = match get_client_secret_by_id(&connection, key_id) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                &format!("Secret key with ID {} not found", key_id),
                json!({"resource_type": "Secret key", "resource_id": key_id.to_string()}),
            );
        }
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    success_json_response(
        json!({
            "secret": secret_value,
            "key": serialize_secret(&updated),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn revoke_secret_key_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
    Path(key_id): Path<i64>,
    payload: Option<Json<SecretKeyRevokeRequest>>,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(record) = (match get_client_secret_by_id(&connection, key_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("Secret key with ID {} not found", key_id),
            json!({"resource_type": "Secret key", "resource_id": key_id.to_string()}),
        );
    };
    if let Err(response) =
        ensure_allowed_secret_user(record.user_id, &correlation_id.0, &state.runtime.config)
    {
        return response;
    }
    if let Err(err) = mark_client_secret_revoked(&connection, key_id) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    let updated = match get_client_secret_by_id(&connection, key_id) {
        Ok(Some(record)) => record,
        Ok(None) => {
            return not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                &format!("Secret key with ID {} not found", key_id),
                json!({"resource_type": "Secret key", "resource_id": key_id.to_string()}),
            );
        }
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let _ = payload.as_ref().and_then(|body| body.reason.as_deref());
    success_json_response(
        json!({"key": serialize_secret(&updated)}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn list_secret_keys_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
    query: Result<Query<SecretKeyListQuery>, QueryRejection>,
) -> Response {
    let query = match query {
        Ok(query) => query.0,
        Err(err) => {
            return validation_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Request validation failed",
                Some(json!({"reason": err.body_text()})),
            );
        }
    };
    if let Some(user_id) = query.user_id {
        if let Err(response) =
            ensure_allowed_secret_user(user_id, &correlation_id.0, &state.runtime.config)
        {
            return response;
        }
    }
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let records = match list_client_secrets(
        &connection,
        query.user_id,
        query.client_id.as_deref(),
        query.status.as_deref(),
    ) {
        Ok(records) => records,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let keys = records
        .into_iter()
        .map(|record| serialize_secret(&record))
        .collect::<Vec<_>>();
    success_json_response(
        json!({"keys": keys}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_telegram_link_status_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(user) = (match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("User with ID {} not found", auth.user_id),
            json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
        );
    };
    success_json_response(
        build_link_status_payload(&user),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn begin_telegram_link_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(_) = (match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("User with ID {} not found", auth.user_id),
            json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
        );
    };
    let expires_at = Utc::now() + Duration::minutes(15);
    let nonce = generate_urlsafe_token(32);
    if let Err(err) = set_link_nonce(&connection, auth.user_id, &nonce, &expires_at.to_rfc3339()) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    success_json_response(
        json!({
            "nonce": nonce,
            "expires_at": expires_at.to_rfc3339().replace("+00:00", "Z"),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn complete_telegram_link_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
    payload: Result<Json<TelegramLinkCompleteRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let Some(user) = (match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    }) else {
        return not_found_response(
            &correlation_id.0,
            &state.runtime.config,
            &format!("User with ID {} not found", auth.user_id),
            json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
        );
    };
    let Some(link_nonce) = user.link_nonce.as_deref() else {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Linking not initiated",
            Some(json!({"field": "nonce"})),
        );
    };
    let Some(link_nonce_expires_at) = parse_datetime(user.link_nonce_expires_at.as_deref()) else {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Linking not initiated",
            Some(json!({"field": "nonce"})),
        );
    };
    if payload.nonce != link_nonce {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Invalid link nonce",
            Some(json!({"field": "nonce"})),
        );
    }
    if link_nonce_expires_at < Utc::now() {
        return validation_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Link nonce expired",
            Some(json!({"field": "nonce"})),
        );
    }
    if let Err(response) = verify_telegram_auth(
        payload.telegram_user_id,
        &payload.auth_hash,
        payload.auth_date,
        payload.username.as_deref(),
        payload.first_name.as_deref(),
        payload.last_name.as_deref(),
        payload.photo_url.as_deref(),
        &correlation_id.0,
        &state.runtime.config,
    ) {
        return response;
    }
    let linked_at = Utc::now().to_rfc3339();
    if let Err(err) = complete_telegram_link(
        &connection,
        auth.user_id,
        payload.telegram_user_id,
        payload.username.as_deref(),
        payload.photo_url.as_deref(),
        payload.first_name.as_deref(),
        payload.last_name.as_deref(),
        &linked_at,
    ) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    let updated_user = match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(Some(user)) => user,
        Ok(None) => {
            return not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                &format!("User with ID {} not found", auth.user_id),
                json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
            );
        }
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    success_json_response(
        build_link_status_payload(&updated_user),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn unlink_telegram_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    if let Err(err) = unlink_telegram(&connection, auth.user_id) {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    let updated_user = match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(Some(user)) => user,
        Ok(None) => {
            return not_found_response(
                &correlation_id.0,
                &state.runtime.config,
                &format!("User with ID {} not found", auth.user_id),
                json!({"resource_type": "User", "resource_id": auth.user_id.to_string()}),
            );
        }
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    success_json_response(
        build_link_status_payload(&updated_user),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_user_preferences_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let user_record = match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let preferences = merge_preferences(
        user_record
            .as_ref()
            .and_then(|user| user.preferences_json.clone()),
    );
    success_json_response(
        json!({
            "userId": auth.user_id,
            "telegramUsername": auth.username,
            "langPreference": preferences.get("lang_preference").cloned().unwrap_or(Value::Null),
            "notificationSettings": preferences.get("notification_settings").cloned().unwrap_or_else(|| json!({})),
            "appSettings": preferences.get("app_settings").cloned().unwrap_or_else(|| json!({})),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn update_user_preferences_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
    payload: Result<Json<UpdatePreferencesRequest>, JsonRejection>,
) -> Response {
    let payload = match parse_json_payload(payload, &correlation_id.0, &state.runtime.config) {
        Ok(payload) => payload.0,
        Err(response) => return response,
    };
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let (user, _) =
        match get_or_create_user(&connection, auth.user_id, auth.username.as_deref(), false) {
            Ok(value) => value,
            Err(err) => {
                return internal_error_response(
                    &correlation_id.0,
                    &state.runtime.config,
                    "Database temporarily unavailable",
                    "DATABASE_ERROR",
                    Some(json!({"reason": err.to_string()})),
                    true,
                    StatusCode::SERVICE_UNAVAILABLE,
                );
            }
        };
    let mut current_prefs = match user.preferences_json {
        Some(Value::Object(map)) => map,
        _ => Map::new(),
    };
    let mut updated_fields = Vec::new();
    if let Some(lang_preference) = payload.lang_preference {
        current_prefs.insert(
            "lang_preference".to_string(),
            Value::String(lang_preference),
        );
        updated_fields.push("lang_preference".to_string());
    }
    if let Some(notification_settings) = payload.notification_settings {
        let mut merged = current_prefs
            .get("notification_settings")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        for (key, value) in notification_settings {
            merged.insert(key.clone(), value);
            updated_fields.push(format!("notification_settings.{key}"));
        }
        current_prefs.insert("notification_settings".to_string(), Value::Object(merged));
    }
    if let Some(app_settings) = payload.app_settings {
        let mut merged = current_prefs
            .get("app_settings")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        for (key, value) in app_settings {
            merged.insert(key.clone(), value);
            updated_fields.push(format!("app_settings.{key}"));
        }
        current_prefs.insert("app_settings".to_string(), Value::Object(merged));
    }
    if let Err(err) =
        update_user_preferences(&connection, auth.user_id, &Value::Object(current_prefs))
    {
        return internal_error_response(
            &correlation_id.0,
            &state.runtime.config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        );
    }
    success_json_response(
        json!({
            "updatedFields": updated_fields,
            "updatedAt": Utc::now().to_rfc3339().replace("+00:00", "Z"),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_user_stats_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    CurrentUser(auth): CurrentUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let summaries = match list_user_summary_rows(&connection, auth.user_id) {
        Ok(rows) => rows,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let user_record = match get_user_by_telegram_id(&connection, auth.user_id) {
        Ok(record) => record,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let total_summaries = summaries.len() as i64;
    let unread_count = summaries.iter().filter(|row| !row.is_read).count() as i64;
    let read_count = total_summaries - unread_count;

    let mut total_reading_time = 0i64;
    let mut topic_counter: HashMap<String, i64> = HashMap::new();
    let mut domain_counter: HashMap<String, i64> = HashMap::new();
    let mut en_count = 0i64;
    let mut ru_count = 0i64;

    for summary in &summaries {
        let payload = ensure_mapping(summary.json_payload_raw.as_deref());
        total_reading_time += payload
            .get("estimated_reading_time_min")
            .and_then(Value::as_i64)
            .unwrap_or_default();

        if let Some(Value::Array(topic_tags)) = payload.get("topic_tags") {
            for tag in topic_tags {
                if let Some(tag) = tag.as_str() {
                    if !tag.is_empty() {
                        *topic_counter.entry(tag.to_ascii_lowercase()).or_default() += 1;
                    }
                }
            }
        }

        let metadata = payload
            .get("metadata")
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default();
        let mut domain = metadata
            .get("domain")
            .and_then(Value::as_str)
            .map(str::to_string);
        if domain.is_none() {
            if let Some(url) = summary.request_normalized_url.as_deref() {
                if let Ok(parsed) = Url::parse(url) {
                    domain = Some(parsed.host_str().unwrap_or_default().to_string());
                }
            }
        }
        if let Some(domain) = domain.filter(|value| !value.is_empty()) {
            *domain_counter.entry(domain).or_default() += 1;
        }

        match summary.lang.as_deref() {
            Some("en") => en_count += 1,
            Some("ru") => ru_count += 1,
            _ => {}
        }
    }

    let average_reading_time = if total_summaries > 0 {
        ((total_reading_time as f64 / total_summaries as f64) * 10.0).round() / 10.0
    } else {
        0.0
    };
    let favorite_topics = top_counter_entries(topic_counter, "topic");
    let favorite_domains = top_counter_entries(domain_counter, "domain");
    let last_summary_at = summaries
        .first()
        .and_then(|row| normalize_datetime_text(row.request_created_at.as_deref()));
    success_json_response(
        json!({
            "totalSummaries": total_summaries,
            "unreadCount": unread_count,
            "readCount": read_count,
            "totalReadingTimeMin": total_reading_time,
            "averageReadingTimeMin": average_reading_time,
            "favoriteTopics": favorite_topics,
            "favoriteDomains": favorite_domains,
            "languageDistribution": {"en": en_count, "ru": ru_count},
            "joinedAt": user_record.as_ref().and_then(|user| normalize_datetime_text(user.created_at.as_deref())),
            "lastSummaryAt": last_summary_at,
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn get_db_info_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
) -> Response {
    let connection = match open_connection(&state.runtime.config.db_path) {
        Ok(connection) => connection,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    let file_size_mb = std::fs::metadata(&state.runtime.config.db_path)
        .map(|metadata| ((metadata.len() as f64 / (1024.0 * 1024.0)) * 10.0).round() / 10.0)
        .unwrap_or(0.0);
    let table_counts = match allowlisted_table_counts(&connection) {
        Ok(rows) => rows
            .into_iter()
            .map(|(table, count)| (table, json!(count)))
            .collect::<Map<String, Value>>(),
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database temporarily unavailable",
                "DATABASE_ERROR",
                Some(json!({"reason": err.to_string()})),
                true,
                StatusCode::SERVICE_UNAVAILABLE,
            );
        }
    };
    success_json_response(
        json!({
            "file_size_mb": file_size_mb,
            "table_counts": table_counts,
            "db_path": state.runtime.config.db_path.display().to_string(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn clear_cache_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    OwnerUser { .. }: OwnerUser,
) -> Response {
    let cleared = match clear_url_cache(&state.runtime.config).await {
        Ok(count) => count,
        Err(response) => return response,
    };
    success_json_response(
        json!({"cleared_keys": cleared}),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn download_database_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    owner: OwnerUser,
    headers: HeaderMap,
) -> Response {
    let dump = match build_db_dump_file(&state.runtime.config, &headers, owner.auth.user_id) {
        Ok(dump) => dump,
        Err(response) => return response,
    };
    let bytes = match fs::read(&dump.path).await {
        Ok(bytes) => bytes,
        Err(err) => {
            return internal_error_response(
                &correlation_id.0,
                &state.runtime.config,
                "Database backup file not found",
                "NOT_FOUND",
                Some(json!({"reason": err.to_string()})),
                false,
                StatusCode::NOT_FOUND,
            );
        }
    };
    let content_type = HeaderValue::from_static("application/x-sqlite3");
    let disposition = HeaderValue::from_str(&format!("attachment; filename=\"{}\"", dump.filename))
        .unwrap_or_else(|_| HeaderValue::from_static("attachment"));
    let etag = HeaderValue::from_str(&dump.etag)
        .unwrap_or_else(|_| HeaderValue::from_static("\"invalid\""));
    let accept_ranges = HeaderValue::from_static("bytes");

    if let Some(range_header) = headers.get(RANGE).and_then(|value| value.to_str().ok()) {
        if let Some((start, end)) = parse_range_header(range_header, bytes.len() as u64) {
            let body = bytes[start as usize..=end as usize].to_vec();
            let content_range =
                HeaderValue::from_str(&format!("bytes {start}-{end}/{}", bytes.len()))
                    .unwrap_or_else(|_| HeaderValue::from_static("bytes */*"));
            return (
                StatusCode::PARTIAL_CONTENT,
                [
                    (CONTENT_TYPE, content_type),
                    (CONTENT_DISPOSITION, disposition),
                    (ETAG, etag),
                    (ACCEPT_RANGES, accept_ranges),
                    (
                        CONTENT_LENGTH,
                        HeaderValue::from_str(&body.len().to_string())
                            .unwrap_or_else(|_| HeaderValue::from_static("0")),
                    ),
                    (CONTENT_RANGE, content_range),
                ],
                body,
            )
                .into_response();
        }
    }

    (
        StatusCode::OK,
        [
            (CONTENT_TYPE, content_type),
            (CONTENT_DISPOSITION, disposition),
            (ETAG, etag),
            (ACCEPT_RANGES, accept_ranges),
            (
                CONTENT_LENGTH,
                HeaderValue::from_str(&bytes.len().to_string())
                    .unwrap_or_else(|_| HeaderValue::from_static("0")),
            ),
        ],
        bytes,
    )
        .into_response()
}

async fn head_database_handler(
    State(state): State<AppState>,
    Extension(_correlation_id): Extension<CorrelationId>,
    owner: OwnerUser,
    headers: HeaderMap,
) -> Response {
    let dump = match build_db_dump_file(&state.runtime.config, &headers, owner.auth.user_id) {
        Ok(dump) => dump,
        Err(response) => return response,
    };
    (
        StatusCode::OK,
        [
            (
                CONTENT_TYPE,
                HeaderValue::from_static("application/x-sqlite3"),
            ),
            (
                CONTENT_DISPOSITION,
                HeaderValue::from_str(&format!("attachment; filename=\"{}\"", dump.filename))
                    .unwrap_or_else(|_| HeaderValue::from_static("attachment")),
            ),
            (
                ETAG,
                HeaderValue::from_str(&dump.etag)
                    .unwrap_or_else(|_| HeaderValue::from_static("\"invalid\"")),
            ),
            (ACCEPT_RANGES, HeaderValue::from_static("bytes")),
            (
                CONTENT_LENGTH,
                HeaderValue::from_str(&dump.len.to_string())
                    .unwrap_or_else(|_| HeaderValue::from_static("0")),
            ),
        ],
    )
        .into_response()
}

fn parse_json_payload<T: DeserializeOwned>(
    payload: Result<Json<T>, JsonRejection>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<Json<T>, Response> {
    payload.map_err(|err| {
        validation_error_response(
            correlation_id,
            config,
            "Request validation failed",
            Some(json!({"reason": err.body_text()})),
        )
    })
}

fn validate_current_user_contract(
    user: &AuthenticatedUser,
    correlation_id: String,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if !config.allowed_user_ids.is_empty() && !config.allowed_user_ids.contains(&user.user_id) {
        return Err(forbidden_response(
            &correlation_id,
            config,
            "User not authorized",
            "FORBIDDEN",
        ));
    }
    validate_client_id(&user.client_id, &correlation_id, config)
}

fn validate_client_id(
    client_id: &str,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    validate_optional_client_id(Some(client_id), correlation_id, config)
}

fn validate_optional_client_id(
    client_id: Option<&str>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    let Some(client_id) = client_id else {
        return Err(validation_error_response(
            correlation_id,
            config,
            "Client ID is required. Please update your app to the latest version.",
            Some(json!({"field": "client_id"})),
        ));
    };
    if client_id.is_empty()
        || client_id.len() > 100
        || !client_id
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.'))
    {
        return Err(validation_error_response(
            correlation_id,
            config,
            "Invalid client ID format.",
            Some(json!({"field": "client_id"})),
        ));
    }
    if !config.allowed_client_ids.is_empty() && !config.allowed_client_ids.contains(client_id) {
        return Err(forbidden_response(
            correlation_id,
            config,
            "Client application not authorized. Please contact administrator.",
            "FORBIDDEN",
        ));
    }
    Ok(())
}

fn verify_telegram_auth(
    user_id: i64,
    auth_hash: &str,
    auth_date: i64,
    username: Option<&str>,
    first_name: Option<&str>,
    last_name: Option<&str>,
    photo_url: Option<&str>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    let current_time = unix_timestamp();
    let age_seconds = current_time - auth_date;
    if age_seconds > 900 {
        return Err(auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            &format!("Authentication expired ({age_seconds} seconds old). Please log in again."),
            None,
            false,
        ));
    }
    if age_seconds < -60 {
        return Err(auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Authentication timestamp is in the future. Check device clock.",
            None,
            false,
        ));
    }
    let Some(bot_token) = config.bot_token.as_ref() else {
        return Err(internal_error_response(
            correlation_id,
            config,
            "Server misconfiguration: BOT_TOKEN is not set.",
            "CONFIGURATION_ERROR",
            Some(json!({"config_key": "BOT_TOKEN"})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    };
    let mut data_check = vec![format!("auth_date={auth_date}"), format!("id={user_id}")];
    if let Some(first_name) = first_name.filter(|value| !value.is_empty()) {
        data_check.push(format!("first_name={first_name}"));
    }
    if let Some(last_name) = last_name.filter(|value| !value.is_empty()) {
        data_check.push(format!("last_name={last_name}"));
    }
    if let Some(photo_url) = photo_url.filter(|value| !value.is_empty()) {
        data_check.push(format!("photo_url={photo_url}"));
    }
    if let Some(username) = username.filter(|value| !value.is_empty()) {
        data_check.push(format!("username={username}"));
    }
    data_check.sort();
    let data_check_string = data_check.join("\n");
    let secret_key = Sha256::digest(bot_token.as_bytes());
    let mut mac = HmacSha256::new_from_slice(secret_key.as_slice()).expect("telegram hmac");
    mac.update(data_check_string.as_bytes());
    let computed_hash = hex_string(&mac.finalize().into_bytes());
    if computed_hash != auth_hash {
        return Err(auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            "Invalid authentication hash. Please try logging in again.",
            None,
            false,
        ));
    }
    if !config.allowed_user_ids.contains(&user_id) {
        return Err(forbidden_response(
            correlation_id,
            config,
            "User not authorized. Contact administrator to request access.",
            "FORBIDDEN",
        ));
    }
    Ok(())
}

fn ensure_secret_login_enabled(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if config.secret_login_enabled {
        return Ok(());
    }
    Err(error_json_response(
        StatusCode::FORBIDDEN,
        "FEATURE_DISABLED",
        "Secret-key login is disabled",
        "configuration",
        false,
        correlation_id.to_string(),
        config,
        Some(json!({"feature": "secret-login"})),
        None,
        Vec::new(),
    ))
}

fn ensure_allowed_secret_user(
    user_id: i64,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if config.allowed_user_ids.contains(&user_id) {
        return Ok(());
    }
    Err(forbidden_response(
        correlation_id,
        config,
        "User not authorized. Contact administrator to request access.",
        "FORBIDDEN",
    ))
}

fn ensure_allowed_oauth_user(
    user_id: i64,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<(), Response> {
    if config.allowed_user_ids.is_empty() || config.allowed_user_ids.contains(&user_id) {
        return Ok(());
    }
    Err(forbidden_response(
        correlation_id,
        config,
        "User not authorized. Contact administrator to request access.",
        "FORBIDDEN",
    ))
}

fn validate_secret_value(
    secret: &str,
    for_login: bool,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<String, Response> {
    let cleaned = secret.trim();
    let length = cleaned.len();
    if length < config.secret_min_length || length > config.secret_max_length {
        if for_login {
            return Err(auth_error_response(
                correlation_id,
                config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                "Invalid secret length",
                None,
                false,
            ));
        }
        return Err(validation_error_response(
            correlation_id,
            config,
            "Invalid secret length",
            Some(json!({"field": "secret"})),
        ));
    }
    Ok(cleaned.to_string())
}

fn hash_secret(secret: &str, salt: &str, config: &ApiRuntimeConfig) -> String {
    let pepper = resolve_secret_pepper(config);
    let mut mac = HmacSha256::new_from_slice(pepper.as_bytes()).expect("secret pepper hmac");
    mac.update(format!("{salt}:{secret}").as_bytes());
    hex_string(&mac.finalize().into_bytes())
}

fn resolve_secret_pepper(config: &ApiRuntimeConfig) -> String {
    if let Some(pepper) = config.secret_pepper.as_ref() {
        return pepper.clone();
    }
    if let Some(secret) = config.jwt_secret_key.as_ref() {
        return secret.clone();
    }
    String::new()
}

fn generate_secret_value(config: &ApiRuntimeConfig) -> String {
    let target_len = config.secret_min_length.max(32);
    let mut candidate = generate_urlsafe_token(target_len);
    if candidate.len() > config.secret_max_length {
        candidate.truncate(config.secret_max_length);
    }
    candidate
}

fn create_access_token(
    user_id: i64,
    username: Option<&str>,
    client_id: Option<&str>,
    config: &ApiRuntimeConfig,
) -> Result<String, Response> {
    let secret = match load_jwt_secret(config) {
        Ok(secret) => secret,
        Err(response) => return Err(response),
    };
    let now = unix_timestamp();
    let claims = AccessTokenClaims {
        user_id,
        username: username.map(str::to_string),
        client_id: client_id.map(str::to_string),
        exp: now + ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type: "access".to_string(),
        iat: now,
    };
    jsonwebtoken::encode(
        &Header::new(Algorithm::HS256),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|err| {
        internal_error_response(
            "",
            config,
            "Authentication failed. Please try again.",
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        )
    })
}

fn issue_refresh_token(
    connection: &rusqlite::Connection,
    user_id: i64,
    client_id: Option<&str>,
    device_info: Option<&str>,
    ip_address: Option<&str>,
    config: &ApiRuntimeConfig,
    correlation_id: &str,
) -> Result<(String, i64), Response> {
    let secret = load_jwt_secret(config)?;
    let now = unix_timestamp();
    let claims = RefreshTokenClaims {
        user_id,
        client_id: client_id.map(str::to_string),
        exp: now + REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        token_type: "refresh".to_string(),
        iat: now,
    };
    let token = jsonwebtoken::encode(
        &Header::new(Algorithm::HS256),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|err| {
        internal_error_response(
            correlation_id,
            config,
            "Authentication failed. Please try again.",
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        )
    })?;
    let token_hash = sha256_hex(token.as_bytes());
    let expires_at = DateTime::<Utc>::from_timestamp(claims.exp, 0)
        .unwrap_or_else(Utc::now)
        .to_rfc3339();
    let record = create_refresh_token(
        connection,
        user_id,
        &token_hash,
        client_id,
        device_info,
        ip_address,
        &expires_at,
    )
    .map_err(|err| {
        internal_error_response(
            correlation_id,
            config,
            "Database temporarily unavailable",
            "DATABASE_ERROR",
            Some(json!({"reason": err.to_string()})),
            true,
            StatusCode::SERVICE_UNAVAILABLE,
        )
    })?;
    Ok((token, record.id))
}

fn load_jwt_secret(config: &ApiRuntimeConfig) -> Result<&str, Response> {
    let Some(secret) = config.jwt_secret_key.as_deref() else {
        return Err(internal_error_response(
            "",
            config,
            "JWT_SECRET_KEY environment variable must be configured. Generate one with: openssl rand -hex 32",
            "CONFIGURATION_ERROR",
            Some(json!({"config_key": "JWT_SECRET_KEY"})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    };
    if secret.is_empty() || secret == "your-secret-key-change-in-production" {
        return Err(internal_error_response(
            "",
            config,
            "JWT_SECRET_KEY environment variable must be set to a secure random value. Generate one with: openssl rand -hex 32",
            "CONFIGURATION_ERROR",
            Some(json!({"config_key": "JWT_SECRET_KEY"})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    }
    if secret.len() < 32 {
        return Err(internal_error_response(
            "",
            config,
            &format!(
                "JWT_SECRET_KEY must be at least 32 characters long. Current length: {}",
                secret.len()
            ),
            "CONFIGURATION_ERROR",
            Some(json!({"config_key": "JWT_SECRET_KEY"})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    }
    Ok(secret)
}

fn decode_refresh_token(
    token: &str,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<RefreshTokenClaims, Response> {
    decode_token(token, correlation_id, config, "refresh")
}

fn decode_token<T>(
    token: &str,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    expected_type: &str,
) -> Result<T, Response>
where
    T: DeserializeOwned + TokenTypeAccessor,
{
    let secret = load_jwt_secret(config)?;
    let mut validation = Validation::new(Algorithm::HS256);
    validation.validate_exp = true;
    let decoded = decode::<T>(
        token,
        &DecodingKey::from_secret(secret.as_bytes()),
        &validation,
    )
    .map_err(|err| match err.kind() {
        jsonwebtoken::errors::ErrorKind::ExpiredSignature => auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "TOKEN_EXPIRED",
            &format!(
                "{} token has expired. Please re-authenticate.",
                expected_type.to_ascii_titlecase()
            ),
            Some(json!({"token_type": expected_type})),
            true,
        ),
        _ => auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "TOKEN_INVALID",
            &format!("Invalid token: {err}"),
            Some(json!({"reason": err.to_string()})),
            false,
        ),
    })?;
    if decoded.claims.token_type() != expected_type {
        return Err(auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "TOKEN_WRONG_TYPE",
            &format!(
                "Wrong token type. Expected {expected_type} token, got {} token.",
                decoded.claims.token_type()
            ),
            Some(json!({"expected": expected_type, "received": decoded.claims.token_type()})),
            false,
        ));
    }
    Ok(decoded.claims)
}

async fn verify_oauth_id_token(
    id_token: &str,
    client_id: &str,
    jwks_url: &str,
    issuers: &[&str],
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    provider_label: &str,
) -> Result<OAuthClaims, Response> {
    let header = decode_header(id_token).map_err(|err| {
        auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            &format!("Invalid {provider_label} ID token: {err}"),
            None,
            false,
        )
    })?;
    let kid = header.kid.ok_or_else(|| {
        auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            &format!("Invalid {provider_label} ID token: missing kid"),
            None,
            false,
        )
    })?;
    let jwks = Client::new()
        .get(jwks_url)
        .send()
        .await
        .map_err(|err| {
            auth_error_response(
                correlation_id,
                config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                &format!("Failed to verify {provider_label} ID token"),
                Some(json!({"reason": err.to_string()})),
                false,
            )
        })?
        .error_for_status()
        .map_err(|err| {
            auth_error_response(
                correlation_id,
                config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                &format!("Failed to verify {provider_label} ID token"),
                Some(json!({"reason": err.to_string()})),
                false,
            )
        })?
        .json::<JwksDocument>()
        .await
        .map_err(|err| {
            auth_error_response(
                correlation_id,
                config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                &format!("Failed to verify {provider_label} ID token"),
                Some(json!({"reason": err.to_string()})),
                false,
            )
        })?;
    let key = jwks
        .keys
        .into_iter()
        .find(|candidate| {
            candidate.kid.as_deref() == Some(kid.as_str())
                && candidate.kty.as_deref() == Some("RSA")
                && candidate.n.is_some()
                && candidate.e.is_some()
                && candidate.use_.as_deref().unwrap_or("sig") == "sig"
        })
        .ok_or_else(|| {
            auth_error_response(
                correlation_id,
                config,
                StatusCode::UNAUTHORIZED,
                "UNAUTHORIZED",
                &format!("Invalid {provider_label} ID token: signing key not found"),
                None,
                false,
            )
        })?;
    let decoding_key = DecodingKey::from_rsa_components(
        key.n.as_deref().unwrap_or_default(),
        key.e.as_deref().unwrap_or_default(),
    )
    .map_err(|err| {
        auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            &format!("Invalid {provider_label} ID token: {err}"),
            None,
            false,
        )
    })?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_audience(&[client_id]);
    validation.set_issuer(issuers);
    let decoded = decode::<OAuthClaims>(id_token, &decoding_key, &validation).map_err(|err| {
        auth_error_response(
            correlation_id,
            config,
            StatusCode::UNAUTHORIZED,
            "UNAUTHORIZED",
            &format!("Invalid {provider_label} ID token: {err}"),
            None,
            false,
        )
    })?;
    Ok(decoded.claims)
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

fn merge_preferences(stored: Option<Value>) -> Map<String, Value> {
    let mut preferences = Map::new();
    preferences.insert(
        "lang_preference".to_string(),
        Value::String("en".to_string()),
    );
    preferences.insert(
        "notification_settings".to_string(),
        json!({"enabled": true, "frequency": "daily"}),
    );
    preferences.insert(
        "app_settings".to_string(),
        json!({"theme": "dark", "font_size": "medium"}),
    );
    if let Some(Value::Object(stored)) = stored {
        if let Some(Value::String(lang_preference)) = stored.get("lang_preference") {
            if !lang_preference.is_empty() {
                preferences.insert(
                    "lang_preference".to_string(),
                    Value::String(lang_preference.clone()),
                );
            }
        }
        if let Some(Value::Object(notification_settings)) = stored.get("notification_settings") {
            let mut merged = preferences
                .get("notification_settings")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            for (key, value) in notification_settings {
                merged.insert(key.clone(), value.clone());
            }
            preferences.insert("notification_settings".to_string(), Value::Object(merged));
        }
        if let Some(Value::Object(app_settings)) = stored.get("app_settings") {
            let mut merged = preferences
                .get("app_settings")
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default();
            for (key, value) in app_settings {
                merged.insert(key.clone(), value.clone());
            }
            preferences.insert("app_settings".to_string(), Value::Object(merged));
        }
    }
    preferences
}

fn ensure_mapping(raw: Option<&str>) -> Map<String, Value> {
    let Some(raw) = raw else {
        return Map::new();
    };
    if raw.trim().is_empty() {
        return Map::new();
    }
    let parsed = serde_json::from_str::<Value>(raw).ok().or_else(|| {
        serde_json::from_str::<String>(raw)
            .ok()
            .and_then(|inner| serde_json::from_str::<Value>(&inner).ok())
    });
    parsed
        .and_then(|value| value.as_object().cloned())
        .unwrap_or_default()
}

fn top_counter_entries(counter: HashMap<String, i64>, key_name: &str) -> Vec<Value> {
    let mut entries = counter.into_iter().collect::<Vec<_>>();
    entries.sort_by(|left, right| right.1.cmp(&left.1).then(left.0.cmp(&right.0)));
    entries
        .into_iter()
        .take(10)
        .map(|(key, count)| json!({key_name: key, "count": count}))
        .collect()
}

fn build_link_status_payload(user: &UserRecord) -> Value {
    let linked = user.linked_telegram_user_id.is_some();
    json!({
        "linked": linked,
        "telegram_user_id": if linked { user.linked_telegram_user_id } else { None },
        "username": if linked { user.linked_telegram_username.clone() } else { None },
        "photo_url": if linked { user.linked_telegram_photo_url.clone() } else { None },
        "first_name": if linked { user.linked_telegram_first_name.clone() } else { None },
        "last_name": if linked { user.linked_telegram_last_name.clone() } else { None },
        "linked_at": if linked { normalize_datetime_text(user.linked_at.as_deref()) } else { None },
        "link_nonce_expires_at": normalize_datetime_text(user.link_nonce_expires_at.as_deref()),
        "link_nonce": user.link_nonce,
    })
}

fn serialize_secret(record: &ClientSecretRecord) -> Value {
    json!({
        "id": record.id,
        "user_id": record.user_id,
        "client_id": record.client_id,
        "status": record.status,
        "label": record.label,
        "description": record.description,
        "expires_at": normalize_datetime_text(record.expires_at.as_deref()),
        "last_used_at": normalize_datetime_text(record.last_used_at.as_deref()),
        "failed_attempts": record.failed_attempts,
        "locked_until": normalize_datetime_text(record.locked_until.as_deref()),
        "created_at": normalize_datetime_text(record.created_at.as_deref()).unwrap_or_default(),
        "updated_at": normalize_datetime_text(record.updated_at.as_deref()).unwrap_or_default(),
    })
}

async fn clear_url_cache(config: &ApiRuntimeConfig) -> Result<i64, Response> {
    let Some(mut connection) = redis_connection(config).await else {
        return Ok(0);
    };
    let pattern = format!("{}:url:*", config.redis_prefix);
    let mut cursor = 0u64;
    let mut deleted = 0i64;
    loop {
        let (next_cursor, keys): (u64, Vec<String>) = redis::cmd("SCAN")
            .cursor_arg(cursor)
            .arg("MATCH")
            .arg(&pattern)
            .arg("COUNT")
            .arg(100)
            .query_async(&mut connection)
            .await
            .map_err(|err| {
                internal_error_response(
                    "",
                    config,
                    &format!("Cache clear failed: {err}"),
                    "PROCESSING_ERROR",
                    Some(json!({"reason": err.to_string()})),
                    false,
                    StatusCode::INTERNAL_SERVER_ERROR,
                )
            })?;
        if !keys.is_empty() {
            let _: i64 = connection.del(&keys).await.unwrap_or_default();
            deleted += keys.len() as i64;
        }
        if next_cursor == 0 {
            break;
        }
        cursor = next_cursor;
    }
    Ok(deleted)
}

async fn redis_connection(config: &ApiRuntimeConfig) -> Option<redis::aio::MultiplexedConnection> {
    if !config.redis_enabled {
        return None;
    }
    let url = super::redis_connection_url(config);
    let client = match redis::Client::open(url) {
        Ok(client) => client,
        Err(_) => return None,
    };
    match client.get_multiplexed_tokio_connection().await {
        Ok(connection) => Some(connection),
        Err(_) => None,
    }
}

fn build_db_dump_file(
    config: &ApiRuntimeConfig,
    request_headers: &HeaderMap,
    user_id: i64,
) -> Result<DbDumpFile, Response> {
    if !config.db_path.exists() {
        return Err(not_found_response(
            "",
            config,
            &format!(
                "Database file with ID {} not found",
                config.db_path.display()
            ),
            json!({"resource_type": "Database file", "resource_id": config.db_path.display().to_string()}),
        ));
    }
    let backup_path = std::env::temp_dir().join(BACKUP_FILENAME);
    if should_regenerate_backup(request_headers, &backup_path) {
        create_backup(config, &backup_path, user_id)?;
    }
    let metadata = std::fs::metadata(&backup_path).map_err(|err| {
        internal_error_response(
            "",
            config,
            "Database backup file not found",
            "NOT_FOUND",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::NOT_FOUND,
        )
    })?;
    let mtime = metadata.modified().unwrap_or_else(|_| SystemTime::now());
    let datetime = DateTime::<Utc>::from(mtime);
    let filename = format!(
        "bite_size_reader_backup_{}.sqlite",
        datetime.format("%Y%m%d_%H%M%S")
    );
    let etag = format!("\"{:x}-{:x}\"", metadata.len(), system_time_secs(mtime));
    Ok(DbDumpFile {
        path: backup_path,
        filename,
        etag,
        len: metadata.len(),
    })
}

fn should_regenerate_backup(request_headers: &HeaderMap, backup_path: &PathBuf) -> bool {
    let lower = request_headers
        .keys()
        .map(|name| name.as_str().to_ascii_lowercase())
        .collect::<Vec<_>>();
    if lower.iter().any(|header| {
        matches!(
            header.as_str(),
            "range" | "if-match" | "if-unmodified-since"
        )
    }) {
        return false;
    }
    let Ok(metadata) = std::fs::metadata(backup_path) else {
        return true;
    };
    let Ok(mtime) = metadata.modified() else {
        return true;
    };
    unix_timestamp() - system_time_secs(mtime) as i64 >= DB_DUMP_CACHE_STALE_SECONDS
}

fn create_backup(
    config: &ApiRuntimeConfig,
    backup_path: &PathBuf,
    _user_id: i64,
) -> Result<(), Response> {
    let temp_path = backup_path.with_extension("sqlite.tmp");
    let _ = std::fs::remove_file(&temp_path);
    let source = open_connection(&config.db_path).map_err(|err| {
        internal_error_response(
            "",
            config,
            &format!("Backup failed: {err}"),
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        )
    })?;
    let mut dest = open_connection(&temp_path).map_err(|err| {
        internal_error_response(
            "",
            config,
            &format!("Backup failed: {err}"),
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        )
    })?;
    Backup::new(&source, &mut dest)
        .and_then(|backup| backup.run_to_completion(5, std::time::Duration::from_millis(250), None))
        .map_err(|err| {
            internal_error_response(
                "",
                config,
                &format!("Backup failed: {err}"),
                "PROCESSING_ERROR",
                Some(json!({"reason": err.to_string()})),
                false,
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        })?;
    std::fs::rename(&temp_path, backup_path).map_err(|err| {
        internal_error_response(
            "",
            config,
            &format!("Backup failed: {err}"),
            "PROCESSING_ERROR",
            Some(json!({"reason": err.to_string()})),
            false,
            StatusCode::INTERNAL_SERVER_ERROR,
        )
    })?;
    Ok(())
}

fn parse_range_header(range_header: &str, total_len: u64) -> Option<(u64, u64)> {
    let range = range_header.strip_prefix("bytes=")?;
    let (start, end) = range.split_once('-')?;
    let start = start.parse::<u64>().ok()?;
    let end = if end.is_empty() {
        total_len.checked_sub(1)?
    } else {
        end.parse::<u64>().ok()?
    };
    if start > end || end >= total_len {
        return None;
    }
    Some((start, end))
}

fn coerce_datetime(
    value: Option<&str>,
    correlation_id: &str,
    config: &ApiRuntimeConfig,
) -> Result<Option<String>, Response> {
    let Some(value) = value else {
        return Ok(None);
    };
    if value.trim().is_empty() {
        return Ok(None);
    }
    parse_datetime(Some(value))
        .map(|value| Some(value.to_rfc3339()))
        .ok_or_else(|| {
            validation_error_response(
                correlation_id,
                config,
                "Request validation failed",
                Some(json!({"field": "expires_at"})),
            )
        })
}

fn parse_datetime(value: Option<&str>) -> Option<DateTime<Utc>> {
    let raw = value?;
    if raw.trim().is_empty() {
        return None;
    }
    if let Ok(parsed) = DateTime::parse_from_rfc3339(raw) {
        return Some(parsed.with_timezone(&Utc));
    }
    if let Ok(parsed) = chrono::NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S%.f") {
        return Some(DateTime::<Utc>::from_naive_utc_and_offset(parsed, Utc));
    }
    if let Ok(parsed) = chrono::NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S") {
        return Some(DateTime::<Utc>::from_naive_utc_and_offset(parsed, Utc));
    }
    None
}

fn auth_error_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    status: StatusCode,
    code: &str,
    message: &str,
    details: Option<Value>,
    retryable: bool,
) -> Response {
    error_json_response(
        status,
        code,
        message,
        "authentication",
        retryable,
        correlation_id.to_string(),
        config,
        details,
        None,
        Vec::new(),
    )
}

fn authentication_invalid_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
) -> Response {
    auth_error_response(
        correlation_id,
        config,
        StatusCode::UNAUTHORIZED,
        "TOKEN_INVALID",
        &format!("Invalid token: {message}"),
        Some(json!({"reason": message})),
        false,
    )
}

fn authentication_required_response(correlation_id: &str, config: &ApiRuntimeConfig) -> Response {
    error_json_response(
        StatusCode::UNAUTHORIZED,
        "UNAUTHORIZED",
        "Authentication required",
        "authentication",
        false,
        correlation_id.to_string(),
        config,
        None,
        None,
        Vec::new(),
    )
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

fn forbidden_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
    code: &str,
) -> Response {
    error_json_response(
        StatusCode::FORBIDDEN,
        code,
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

fn not_found_response(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    message: &str,
    details: Value,
) -> Response {
    error_json_response(
        StatusCode::NOT_FOUND,
        "NOT_FOUND",
        message,
        "not_found",
        false,
        correlation_id.to_string(),
        config,
        Some(details),
        None,
        Vec::new(),
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

fn sha256_hex(bytes: &[u8]) -> String {
    hex_string(&Sha256::digest(bytes))
}

fn hex_string(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn generate_urlsafe_token(bytes_len: usize) -> String {
    let mut bytes = vec![0u8; bytes_len];
    rand::thread_rng().fill_bytes(&mut bytes);
    URL_SAFE_NO_PAD.encode(bytes)
}

fn generate_hex_token(bytes_len: usize) -> String {
    let mut bytes = vec![0u8; bytes_len];
    rand::thread_rng().fill_bytes(&mut bytes);
    hex_string(&bytes)
}

fn system_time_secs(value: SystemTime) -> u64 {
    value
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or_default()
}

fn unix_timestamp() -> i64 {
    Utc::now().timestamp()
}

fn set_of<const N: usize>(methods: [&str; N]) -> BTreeSet<String> {
    methods.into_iter().map(str::to_string).collect()
}

trait TokenTypeAccessor {
    fn token_type(&self) -> &str;
}

impl TokenTypeAccessor for AccessTokenClaims {
    fn token_type(&self) -> &str {
        &self.token_type
    }
}

impl TokenTypeAccessor for RefreshTokenClaims {
    fn token_type(&self) -> &str {
        &self.token_type
    }
}

trait TitleCase {
    fn to_ascii_titlecase(&self) -> String;
}

impl TitleCase for str {
    fn to_ascii_titlecase(&self) -> String {
        let mut chars = self.chars();
        match chars.next() {
            Some(first) => format!("{}{}", first.to_ascii_uppercase(), chars.as_str()),
            None => String::new(),
        }
    }
}
