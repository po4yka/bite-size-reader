use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

use axum::extract::{OriginalUri, Request, State};
use axum::http::header::{AUTHORIZATION, CONTENT_TYPE, RETRY_AFTER};
use axum::http::{HeaderName, HeaderValue, Method, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{Html, IntoResponse, Response};
use axum::routing::{get, MethodRouter};
use axum::{Extension, Json, Router};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use bsr_interface_router::{
    resolve_mobile_route, MobileRouteDecision as InterfaceRouteDecision, MobileRouteInput,
};
use chrono::Utc;
use hmac::{Hmac, Mac};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::Sha256;
use thiserror::Error;
use tokio::fs;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tower_http::cors::{AllowHeaders, AllowMethods, AllowOrigin, CorsLayer};
use tower_http::services::ServeDir;
use url::form_urlencoded;

type HmacSha256 = Hmac<Sha256>;

const DEFAULT_DOCS_HTML: &str = r#"<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Bite-Size Reader API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
      window.onload = function () {
        window.ui = SwaggerUIBundle({
          url: '/openapi.json',
          dom_id: '#swagger-ui',
          oauth2RedirectUrl: window.location.origin + '/docs/oauth2-redirect',
          presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
          layout: 'StandaloneLayout'
        });
      };
    </script>
  </body>
</html>"#;

const DEFAULT_REDOC_HTML: &str = r#"<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Bite-Size Reader API Reference</title>
  </head>
  <body>
    <redoc spec-url="/openapi.json"></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
  </body>
</html>"#;

const DEFAULT_SWAGGER_OAUTH_REDIRECT_HTML: &str = r#"<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Swagger UI OAuth Redirect</title>
  </head>
  <body>
    <script>
      'use strict';
      function run() {
        var oauth2 = window.opener.swaggerUIRedirectOauth2;
        var sentState = oauth2.state;
        var redirectUrl = oauth2.redirectUrl;
        var isValid = {
          state: location.hash.indexOf('state=') !== -1 || location.search.indexOf('state=') !== -1
        };
        if (isValid.state) {
          oauth2.callback({ auth: { code: location.search, token: location.hash }, redirectUrl: redirectUrl });
        } else {
          oauth2.errCb({ auth: { code: location.search, token: location.hash }, source: 'auth', level: 'warning', message: 'OAuth redirect missing state' });
        }
        window.close();
      }
      run();
    </script>
  </body>
</html>"#;

#[derive(Debug, Error)]
pub enum ApiRuntimeError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("yaml error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, PartialEq)]
pub struct ApiRuntimeConfig {
    pub host: String,
    pub port: u16,
    pub db_path: PathBuf,
    pub allowed_origins: Vec<String>,
    pub openapi_yaml_path: PathBuf,
    pub static_dir: PathBuf,
    pub app_version: String,
    pub app_build: Option<String>,
    pub jwt_secret_key: Option<String>,
    pub bot_token: Option<String>,
    pub allowed_user_ids: HashSet<i64>,
    pub api_rate_limit_window_seconds: i64,
    pub api_rate_limit_cooldown_multiplier: f64,
    pub api_rate_limit_default: usize,
    pub api_rate_limit_summaries: usize,
    pub api_rate_limit_requests: usize,
    pub api_rate_limit_search: usize,
}

impl ApiRuntimeConfig {
    pub fn from_env() -> Self {
        let repo_root = project_root();
        let default_static_dir = repo_root.join("app").join("static");
        let default_openapi_yaml = repo_root
            .join("docs")
            .join("openapi")
            .join("mobile_api.yaml");

        Self {
            host: std::env::var("API_HOST").unwrap_or_else(|_| "0.0.0.0".to_string()),
            port: parse_u16_env("API_PORT", 8000),
            db_path: std::env::var("DB_PATH")
                .map(PathBuf::from)
                .unwrap_or_else(|_| PathBuf::from("/data/app.db")),
            allowed_origins: parse_allowed_origins(),
            openapi_yaml_path: std::env::var("MOBILE_API_OPENAPI_SPEC")
                .map(PathBuf::from)
                .unwrap_or(default_openapi_yaml),
            static_dir: std::env::var("MOBILE_API_STATIC_DIR")
                .map(PathBuf::from)
                .unwrap_or(default_static_dir),
            app_version: std::env::var("APP_VERSION").unwrap_or_else(|_| "1.0.0".to_string()),
            app_build: std::env::var("APP_BUILD")
                .ok()
                .and_then(|value| (!value.trim().is_empty()).then_some(value)),
            jwt_secret_key: std::env::var("JWT_SECRET_KEY")
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty()),
            bot_token: std::env::var("BOT_TOKEN")
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty()),
            allowed_user_ids: parse_allowed_user_ids(),
            api_rate_limit_window_seconds: parse_i64_env("API_RATE_LIMIT_WINDOW_SECONDS", 60),
            api_rate_limit_cooldown_multiplier: parse_f64_env(
                "API_RATE_LIMIT_COOLDOWN_MULTIPLIER",
                2.0,
            ),
            api_rate_limit_default: parse_usize_env("API_RATE_LIMIT_DEFAULT", 100),
            api_rate_limit_summaries: parse_usize_env("API_RATE_LIMIT_SUMMARIES", 200),
            api_rate_limit_requests: parse_usize_env("API_RATE_LIMIT_REQUESTS", 10),
            api_rate_limit_search: parse_usize_env("API_RATE_LIMIT_SEARCH", 50),
        }
    }

    pub fn web_index_path(&self) -> PathBuf {
        self.static_dir.join("web").join("index.html")
    }
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct RegisteredRoute {
    pub path: String,
    pub methods: Vec<String>,
    pub source: String,
}

#[derive(Debug, Clone)]
pub struct AppState {
    runtime: Arc<ApiRuntime>,
}

#[derive(Debug)]
struct ApiRuntime {
    config: ApiRuntimeConfig,
    openapi_json: Value,
    route_manifest: Vec<RegisteredRoute>,
    local_rate_limits: Mutex<HashMap<String, Vec<i64>>>,
}

#[derive(Debug, Clone)]
struct CorrelationId(String);

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
struct AuthenticatedUser {
    user_id: i64,
    username: Option<String>,
}

#[derive(Debug, Clone)]
struct ResolvedRoute(InterfaceRouteDecision);

#[derive(Debug, Deserialize)]
struct JwtHeader {
    alg: String,
}

#[derive(Debug, Deserialize)]
struct JwtClaims {
    user_id: Value,
    username: Option<String>,
    exp: Option<i64>,
}

pub async fn build_state_from_env() -> Result<AppState, ApiRuntimeError> {
    build_state(ApiRuntimeConfig::from_env()).await
}

pub async fn build_state(config: ApiRuntimeConfig) -> Result<AppState, ApiRuntimeError> {
    let openapi_json = load_openapi_json(&config.openapi_yaml_path).await?;
    let route_manifest = build_route_manifest(&openapi_json);
    Ok(AppState {
        runtime: Arc::new(ApiRuntime {
            config,
            openapi_json,
            route_manifest,
            local_rate_limits: Mutex::new(HashMap::new()),
        }),
    })
}

pub fn build_router(state: AppState) -> Router<AppState> {
    let manual_routes = manual_route_map();
    let mut router = Router::new()
        .route("/", get(root_handler))
        .route("/health", get(health_handler))
        .route("/health/detailed", get(detailed_health_handler))
        .route("/health/ready", get(readiness_handler))
        .route("/health/live", get(liveness_handler))
        .route("/metrics", get(metrics_handler))
        .route("/openapi.json", get(openapi_json_handler))
        .route("/docs", get(docs_handler))
        .route("/redoc", get(redoc_handler))
        .route("/docs/oauth2-redirect", get(swagger_oauth_redirect_handler))
        .route("/web", get(web_index_handler))
        .route("/web/{*path}", get(web_index_handler))
        .nest_service(
            "/static",
            ServeDir::new(state.runtime.config.static_dir.clone()),
        );

    for (path, methods) in spec_route_map(&state.runtime.route_manifest) {
        let manual_methods = manual_routes
            .get(path.as_str())
            .cloned()
            .unwrap_or_default();
        let placeholder_methods: Vec<String> = methods
            .into_iter()
            .filter(|method| !manual_methods.contains(method))
            .collect();
        if placeholder_methods.is_empty() {
            continue;
        }
        router = router.route(path.as_str(), build_method_router(&placeholder_methods));
    }

    router
        .fallback(not_found_handler)
        .layer(build_cors_layer(&state.runtime.config))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            rate_limit_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_guard_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state.clone(),
            webapp_auth_middleware,
        ))
        .layer(middleware::from_fn_with_state(
            state,
            correlation_id_middleware,
        ))
}

pub async fn serve(state: AppState) -> Result<(), ApiRuntimeError> {
    let address = format!(
        "{}:{}",
        state.runtime.config.host, state.runtime.config.port
    );
    let listener = TcpListener::bind(address).await?;
    axum::serve(listener, build_router(state.clone()).with_state(state)).await?;
    Ok(())
}

pub fn route_manifest(state: &AppState) -> &[RegisteredRoute] {
    &state.runtime.route_manifest
}

pub fn route_manifest_json(state: &AppState) -> Value {
    serde_json::to_value(route_manifest(state)).unwrap_or_else(|_| Value::Array(Vec::new()))
}

pub fn openapi_json(state: &AppState) -> &Value {
    &state.runtime.openapi_json
}

async fn correlation_id_middleware(
    State(_state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    let correlation_id = request
        .headers()
        .get("X-Correlation-ID")
        .and_then(|value| value.to_str().ok())
        .filter(|value| !value.trim().is_empty())
        .map(str::to_string)
        .unwrap_or_else(generate_correlation_id);

    request
        .extensions_mut()
        .insert(CorrelationId(correlation_id.clone()));
    let mut response = next.run(request).await;
    if let Ok(header_value) = HeaderValue::from_str(&correlation_id) {
        response
            .headers_mut()
            .insert(HeaderName::from_static("x-correlation-id"), header_value);
    }
    response
}

async fn webapp_auth_middleware(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    if request.headers().contains_key(AUTHORIZATION) {
        return next.run(request).await;
    }

    let init_data = request
        .headers()
        .get("X-Telegram-Init-Data")
        .and_then(|value| value.to_str().ok())
        .filter(|value| !value.trim().is_empty());

    if let Some(raw_init_data) = init_data {
        if let Ok(user) = verify_telegram_webapp_init_data(raw_init_data, &state.runtime.config) {
            request.extensions_mut().insert(user);
        }
    }

    next.run(request).await
}

async fn auth_guard_middleware(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    let resolved_path = request
        .uri()
        .path_and_query()
        .map(|value| value.as_str().to_string())
        .unwrap_or_else(|| request.uri().path().to_string());
    let decision = resolve_mobile_route(&MobileRouteInput {
        method: request.method().to_string(),
        path: resolved_path,
    });
    request
        .extensions_mut()
        .insert(ResolvedRoute(decision.clone()));

    match resolve_authenticated_user(
        request.headers(),
        request.extensions(),
        &state.runtime.config,
    ) {
        Ok(Some(user)) => {
            request.extensions_mut().insert(user);
        }
        Ok(None) => {}
        Err(message) => {
            if decision.requires_auth {
                let correlation_id = request
                    .extensions()
                    .get::<CorrelationId>()
                    .map(|value| value.0.clone())
                    .unwrap_or_default();
                return error_json_response(
                    StatusCode::UNAUTHORIZED,
                    "AUTH_TOKEN_INVALID",
                    &message,
                    "authentication",
                    false,
                    correlation_id,
                    &state.runtime.config,
                    None,
                    None,
                    Vec::new(),
                );
            }
        }
    }

    if decision.requires_auth && request.extensions().get::<AuthenticatedUser>().is_none() {
        let correlation_id = request
            .extensions()
            .get::<CorrelationId>()
            .map(|value| value.0.clone())
            .unwrap_or_default();
        return error_json_response(
            StatusCode::UNAUTHORIZED,
            "AUTH_TOKEN_INVALID",
            "Authentication required",
            "authentication",
            false,
            correlation_id,
            &state.runtime.config,
            None,
            None,
            Vec::new(),
        );
    }

    next.run(request).await
}

async fn rate_limit_middleware(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    if request.method() == Method::OPTIONS {
        return next.run(request).await;
    }

    let correlation_id = request
        .extensions()
        .get::<CorrelationId>()
        .map(|value| value.0.clone())
        .unwrap_or_default();

    let decision = request
        .extensions()
        .get::<ResolvedRoute>()
        .map(|value| value.0.clone())
        .unwrap_or_else(|| {
            resolve_mobile_route(&MobileRouteInput {
                method: request.method().to_string(),
                path: request.uri().path().to_string(),
            })
        });

    let bucket_limit = match decision.rate_limit_bucket.as_str() {
        "summaries" => state.runtime.config.api_rate_limit_summaries,
        "requests" => state.runtime.config.api_rate_limit_requests,
        "search" => state.runtime.config.api_rate_limit_search,
        _ => state.runtime.config.api_rate_limit_default,
    };

    let now = unix_timestamp();
    let window = state.runtime.config.api_rate_limit_window_seconds.max(1);
    let window_start = (now / window) * window;
    let actor = resolve_rate_limit_actor(&request, &state.runtime.config)
        .unwrap_or_else(|| "unknown".to_string());
    let key = format!("{actor}:{window_start}");

    let (allowed, remaining) = {
        let mut local_limits = state.runtime.local_rate_limits.lock().await;
        let bucket = local_limits.entry(key).or_default();
        bucket.retain(|timestamp| *timestamp >= window_start);
        if bucket.len() >= bucket_limit {
            (false, 0)
        } else {
            bucket.push(now);
            (true, bucket_limit.saturating_sub(bucket.len()))
        }
    };

    if !allowed {
        let retry_after = ((window_start + window) - now)
            .max((window as f64 * state.runtime.config.api_rate_limit_cooldown_multiplier) as i64);
        return error_json_response(
            StatusCode::TOO_MANY_REQUESTS,
            "RATE_LIMIT_EXCEEDED",
            &format!("Rate limit exceeded. Try again in {retry_after} seconds."),
            "rate_limit",
            true,
            correlation_id,
            &state.runtime.config,
            None,
            Some(retry_after),
            vec![
                ("x-ratelimit-limit", bucket_limit.to_string()),
                ("x-ratelimit-remaining", "0".to_string()),
                ("x-ratelimit-reset", (window_start + window).to_string()),
                (RETRY_AFTER.as_str(), retry_after.to_string()),
            ],
        );
    }

    let mut response = next.run(request).await;
    if let Ok(value) = HeaderValue::from_str(&bucket_limit.to_string()) {
        response
            .headers_mut()
            .insert(HeaderName::from_static("x-ratelimit-limit"), value);
    }
    if let Ok(value) = HeaderValue::from_str(&remaining.to_string()) {
        response
            .headers_mut()
            .insert(HeaderName::from_static("x-ratelimit-remaining"), value);
    }
    if let Ok(value) = HeaderValue::from_str(&(window_start + window).to_string()) {
        response
            .headers_mut()
            .insert(HeaderName::from_static("x-ratelimit-reset"), value);
    }
    response
}

async fn root_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    success_json_response(
        json!({
            "service": "Bite-Size Reader Mobile API",
            "version": state.runtime.config.app_version,
            "docs": "/docs",
            "health": "/health",
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn health_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    success_json_response(
        json!({
            "status": "healthy",
            "timestamp": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn detailed_health_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    let started = Instant::now();
    let database = database_component_status(&state.runtime.config);
    let redis_enabled = parse_bool_env("REDIS_ENABLED", true);
    let redis = if redis_enabled {
        json!({
            "status": "unavailable",
            "latency_ms": serde_json::Value::Null,
            "details": {
                "backend": "not-yet-ported",
            },
        })
    } else {
        json!({
            "status": "disabled",
            "latency_ms": 0.0,
        })
    };
    let scraper = json!({
        "status": "unknown",
        "latency_ms": serde_json::Value::Null,
        "details": {
            "backend": "not-yet-ported",
        },
    });
    let circuit_breakers = json!({
        "firecrawl": {"state": "unknown", "info": "Not integrated"},
        "openrouter": {"state": "unknown", "info": "Not integrated"},
    });

    let db_healthy = database
        .get("status")
        .and_then(Value::as_str)
        .is_some_and(|value| value == "healthy");
    let redis_healthy = redis
        .get("status")
        .and_then(Value::as_str)
        .is_some_and(|value| matches!(value, "healthy" | "disabled"));
    let mut health_score = 0.0;
    if db_healthy {
        health_score += 50.0;
    }
    if redis_healthy {
        health_score += 50.0;
    }

    let overall_status = if health_score >= 100.0 {
        "healthy"
    } else if health_score >= 50.0 {
        "degraded"
    } else {
        "unhealthy"
    };

    success_json_response(
        json!({
            "status": overall_status,
            "health_score": health_score,
            "timestamp": iso_timestamp(),
            "total_latency_ms": round_millis(started.elapsed()),
            "components": {
                "database": database,
                "redis": redis,
                "scraper": scraper,
                "circuit_breakers": circuit_breakers,
            },
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn readiness_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    if check_database(&state.runtime.config).is_ok() {
        return success_json_response(
            json!({
                "ready": true,
                "timestamp": iso_timestamp(),
            }),
            correlation_id.0,
            &state.runtime.config,
        );
    }

    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({
            "ready": false,
            "error": "Database not ready",
            "timestamp": iso_timestamp(),
        })),
    )
        .into_response()
}

async fn liveness_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    success_json_response(
        json!({
            "alive": true,
            "timestamp": iso_timestamp(),
        }),
        correlation_id.0,
        &state.runtime.config,
    )
}

async fn metrics_handler() -> Response {
    (
        StatusCode::OK,
        [(
            CONTENT_TYPE,
            HeaderValue::from_static("text/plain; charset=utf-8"),
        )],
        "# Prometheus metrics not available (prometheus_client not installed)\n",
    )
        .into_response()
}

async fn openapi_json_handler(State(state): State<AppState>) -> Response {
    Json(state.runtime.openapi_json.clone()).into_response()
}

async fn docs_handler() -> Response {
    Html(DEFAULT_DOCS_HTML).into_response()
}

async fn redoc_handler() -> Response {
    Html(DEFAULT_REDOC_HTML).into_response()
}

async fn swagger_oauth_redirect_handler() -> Response {
    Html(DEFAULT_SWAGGER_OAUTH_REDIRECT_HTML).into_response()
}

async fn web_index_handler(State(state): State<AppState>) -> Response {
    match fs::read(state.runtime.config.web_index_path()).await {
        Ok(bytes) => (
            StatusCode::OK,
            [(
                CONTENT_TYPE,
                HeaderValue::from_static("text/html; charset=utf-8"),
            )],
            bytes,
        )
            .into_response(),
        Err(_) => (StatusCode::NOT_FOUND, "Web interface is not built").into_response(),
    }
}

async fn spec_placeholder_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
    Extension(route): Extension<ResolvedRoute>,
    OriginalUri(uri): OriginalUri,
) -> Response {
    error_json_response(
        StatusCode::NOT_IMPLEMENTED,
        "INTERNAL_ERROR",
        &format!(
            "Rust API route is registered but not implemented yet: {} ({})",
            uri.path(),
            route.0.route_key
        ),
        "internal",
        false,
        correlation_id.0,
        &state.runtime.config,
        Some(json!({
            "route_key": route.0.route_key,
            "path": uri.path(),
        })),
        None,
        Vec::new(),
    )
}

async fn not_found_handler(
    State(state): State<AppState>,
    Extension(correlation_id): Extension<CorrelationId>,
) -> Response {
    error_json_response(
        StatusCode::NOT_FOUND,
        "RESOURCE_NOT_FOUND",
        "Resource not found",
        "not_found",
        false,
        correlation_id.0,
        &state.runtime.config,
        None,
        None,
        Vec::new(),
    )
}

fn success_json_response(
    data: Value,
    correlation_id: String,
    config: &ApiRuntimeConfig,
) -> Response {
    (
        StatusCode::OK,
        Json(json!({
            "success": true,
            "data": data,
            "meta": build_meta(&correlation_id, config, None, None),
        })),
    )
        .into_response()
}

fn error_json_response(
    status: StatusCode,
    code: &str,
    message: &str,
    error_type: &str,
    retryable: bool,
    correlation_id: String,
    config: &ApiRuntimeConfig,
    details: Option<Value>,
    retry_after: Option<i64>,
    headers: Vec<(&str, String)>,
) -> Response {
    let normalized_details = match (details, retry_after) {
        (Some(value), _) => Some(value),
        (None, Some(value)) => Some(json!({"retry_after": value})),
        (None, None) => None,
    };
    let mut response = (
        status,
        Json(json!({
            "success": false,
            "error": {
                "code": code,
                "errorType": error_type,
                "message": message,
                "retryable": retryable,
                "details": normalized_details,
                "correlation_id": correlation_id,
                "retry_after": retry_after,
            },
            "meta": build_meta(&correlation_id, config, None, None),
        })),
    )
        .into_response();

    for (name, value) in headers {
        if let (Ok(header_name), Ok(header_value)) = (
            HeaderName::from_bytes(name.as_bytes()),
            HeaderValue::from_str(&value),
        ) {
            response.headers_mut().insert(header_name, header_value);
        }
    }
    response
}

fn build_meta(
    correlation_id: &str,
    config: &ApiRuntimeConfig,
    pagination: Option<Value>,
    debug: Option<Value>,
) -> Value {
    json!({
        "correlation_id": correlation_id,
        "timestamp": iso_timestamp(),
        "version": config.app_version,
        "build": config.app_build,
        "pagination": pagination,
        "debug": debug,
    })
}

fn build_cors_layer(config: &ApiRuntimeConfig) -> CorsLayer {
    let origins: Vec<HeaderValue> = config
        .allowed_origins
        .iter()
        .filter_map(|origin| HeaderValue::from_str(origin).ok())
        .collect();

    CorsLayer::new()
        .allow_credentials(true)
        .allow_methods(AllowMethods::list([
            Method::GET,
            Method::POST,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
            Method::HEAD,
        ]))
        .allow_headers(AllowHeaders::list([
            AUTHORIZATION,
            CONTENT_TYPE,
            HeaderName::from_static("x-correlation-id"),
            HeaderName::from_static("x-telegram-init-data"),
        ]))
        .allow_origin(AllowOrigin::list(origins))
}

fn build_method_router(methods: &[String]) -> MethodRouter<AppState> {
    let mut router = MethodRouter::new();
    for method in methods {
        router = match method.as_str() {
            "GET" => router.get(spec_placeholder_handler),
            "POST" => router.post(spec_placeholder_handler),
            "PATCH" => router.patch(spec_placeholder_handler),
            "DELETE" => router.delete(spec_placeholder_handler),
            "PUT" => router.put(spec_placeholder_handler),
            "HEAD" => router.head(spec_placeholder_handler),
            _ => router,
        };
    }
    router
}

async fn load_openapi_json(path: &Path) -> Result<Value, ApiRuntimeError> {
    let raw = fs::read_to_string(path).await?;
    let yaml_value: serde_yaml::Value = serde_yaml::from_str(&raw)?;
    Ok(serde_json::to_value(yaml_value)?)
}

fn build_route_manifest(openapi_json: &Value) -> Vec<RegisteredRoute> {
    let mut manifest = Vec::new();
    for (path, methods) in manual_route_map() {
        manifest.push(RegisteredRoute {
            path: path.to_string(),
            methods: methods.into_iter().collect(),
            source: "manual".to_string(),
        });
    }

    let spec_paths = openapi_json
        .get("paths")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    for (path, methods) in spec_paths {
        let mut normalized_methods = BTreeSet::new();
        if let Some(method_map) = methods.as_object() {
            for method in method_map.keys() {
                let method_upper = method.to_uppercase();
                if matches!(
                    method_upper.as_str(),
                    "GET" | "POST" | "PATCH" | "DELETE" | "PUT" | "HEAD"
                ) {
                    normalized_methods.insert(method_upper);
                }
            }
        }
        if normalized_methods.is_empty() {
            continue;
        }
        manifest.push(RegisteredRoute {
            path,
            methods: normalized_methods.into_iter().collect(),
            source: "openapi".to_string(),
        });
    }

    manifest.sort_by(|left, right| {
        left.path
            .cmp(&right.path)
            .then(left.source.cmp(&right.source))
    });
    manifest
}

fn manual_route_map() -> BTreeMap<&'static str, BTreeSet<String>> {
    let mut routes = BTreeMap::new();
    routes.insert("/", set_of(["GET"]));
    routes.insert("/health", set_of(["GET"]));
    routes.insert("/health/detailed", set_of(["GET"]));
    routes.insert("/health/ready", set_of(["GET"]));
    routes.insert("/health/live", set_of(["GET"]));
    routes.insert("/metrics", set_of(["GET"]));
    routes.insert("/openapi.json", set_of(["GET"]));
    routes.insert("/docs", set_of(["GET"]));
    routes.insert("/redoc", set_of(["GET"]));
    routes.insert("/docs/oauth2-redirect", set_of(["GET"]));
    routes.insert("/web", set_of(["GET"]));
    routes.insert("/web/{*path}", set_of(["GET"]));
    routes.insert("/static/{*path}", set_of(["GET"]));
    routes
}

fn spec_route_map(manifest: &[RegisteredRoute]) -> BTreeMap<String, Vec<String>> {
    let mut routes = BTreeMap::new();
    for route in manifest {
        if route.source != "openapi" {
            continue;
        }
        routes.insert(route.path.clone(), route.methods.clone());
    }
    routes
}

fn set_of<const N: usize>(methods: [&str; N]) -> BTreeSet<String> {
    methods.into_iter().map(str::to_string).collect()
}

fn resolve_authenticated_user(
    headers: &axum::http::HeaderMap,
    extensions: &http::Extensions,
    config: &ApiRuntimeConfig,
) -> Result<Option<AuthenticatedUser>, String> {
    if let Some(header_value) = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
    {
        let Some(token) = header_value.strip_prefix("Bearer ").map(str::trim) else {
            return Err("Invalid authorization header".to_string());
        };
        return decode_jwt_user(token, config).map(Some);
    }

    Ok(extensions.get::<AuthenticatedUser>().cloned())
}

fn resolve_rate_limit_actor(request: &Request, config: &ApiRuntimeConfig) -> Option<String> {
    if let Some(user) = request.extensions().get::<AuthenticatedUser>() {
        return Some(user.user_id.to_string());
    }

    request
        .headers()
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .and_then(|token| decode_jwt_user(token.trim(), config).ok())
        .map(|user| user.user_id.to_string())
}

fn decode_jwt_user(token: &str, config: &ApiRuntimeConfig) -> Result<AuthenticatedUser, String> {
    let Some(secret) = config.jwt_secret_key.as_ref() else {
        return Err("JWT secret is not configured".to_string());
    };

    let mut segments = token.split('.');
    let Some(header_segment) = segments.next() else {
        return Err("Invalid JWT format".to_string());
    };
    let Some(claims_segment) = segments.next() else {
        return Err("Invalid JWT format".to_string());
    };
    let Some(signature_segment) = segments.next() else {
        return Err("Invalid JWT format".to_string());
    };
    if segments.next().is_some() {
        return Err("Invalid JWT format".to_string());
    }

    let header_bytes = URL_SAFE_NO_PAD
        .decode(header_segment)
        .map_err(|_| "Invalid JWT header encoding".to_string())?;
    let header: JwtHeader =
        serde_json::from_slice(&header_bytes).map_err(|_| "Invalid JWT header".to_string())?;
    if header.alg != "HS256" {
        return Err("Unsupported JWT algorithm".to_string());
    }

    let signature = URL_SAFE_NO_PAD
        .decode(signature_segment)
        .map_err(|_| "Invalid JWT signature encoding".to_string())?;
    let signed_payload = format!("{header_segment}.{claims_segment}");
    let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).map_err(|err| err.to_string())?;
    mac.update(signed_payload.as_bytes());
    mac.verify_slice(&signature)
        .map_err(|_| "Invalid JWT signature".to_string())?;

    let claims_bytes = URL_SAFE_NO_PAD
        .decode(claims_segment)
        .map_err(|_| "Invalid JWT claims encoding".to_string())?;
    let claims: JwtClaims =
        serde_json::from_slice(&claims_bytes).map_err(|_| "Invalid JWT claims".to_string())?;
    if let Some(exp) = claims.exp {
        if exp <= unix_timestamp() {
            return Err("Signature has expired".to_string());
        }
    }

    let user_id = match claims.user_id {
        Value::Number(number) => number
            .as_i64()
            .ok_or_else(|| "JWT user_id is not an integer".to_string())?,
        Value::String(value) => value
            .parse::<i64>()
            .map_err(|_| "JWT user_id is not numeric".to_string())?,
        _ => return Err("JWT user_id is missing".to_string()),
    };

    Ok(AuthenticatedUser {
        user_id,
        username: claims.username,
    })
}

fn verify_telegram_webapp_init_data(
    init_data: &str,
    config: &ApiRuntimeConfig,
) -> Result<AuthenticatedUser, String> {
    if init_data.trim().is_empty() {
        return Err("Empty initData".to_string());
    }

    let Some(bot_token) = config.bot_token.as_ref() else {
        return Err("Bot token not configured".to_string());
    };

    let mut parsed: HashMap<String, String> = form_urlencoded::parse(init_data.as_bytes())
        .into_owned()
        .collect();
    let Some(received_hash) = parsed.remove("hash") else {
        return Err("Missing hash in initData".to_string());
    };

    let mut pairs: Vec<String> = parsed
        .iter()
        .map(|(key, value)| format!("{key}={value}"))
        .collect();
    pairs.sort();
    let data_check_string = pairs.join("\n");

    let mut secret = HmacSha256::new_from_slice(b"WebAppData").map_err(|err| err.to_string())?;
    secret.update(bot_token.as_bytes());
    let secret_key = secret.finalize().into_bytes();

    let mut computed = HmacSha256::new_from_slice(&secret_key).map_err(|err| err.to_string())?;
    computed.update(data_check_string.as_bytes());
    let computed_hash = hex_string(&computed.finalize().into_bytes());

    if computed_hash != received_hash {
        return Err("Invalid initData signature".to_string());
    }

    let auth_date = parsed
        .get("auth_date")
        .ok_or_else(|| "Missing auth_date in initData".to_string())?
        .parse::<i64>()
        .map_err(|_| "Invalid auth_date format".to_string())?;

    let now = unix_timestamp();
    if now - auth_date > 960 {
        return Err("initData has expired".to_string());
    }
    if auth_date - now > 60 {
        return Err("initData auth_date is in the future".to_string());
    }

    let user_json = parsed
        .get("user")
        .ok_or_else(|| "Missing user in initData".to_string())?;
    let user_payload: Value =
        serde_json::from_str(user_json).map_err(|_| "Invalid user JSON in initData".to_string())?;
    let user_id = user_payload
        .get("id")
        .and_then(Value::as_i64)
        .ok_or_else(|| "Missing user id in initData".to_string())?;

    if config.allowed_user_ids.is_empty() {
        return Err("No authorized users configured".to_string());
    }
    if !config.allowed_user_ids.contains(&user_id) {
        return Err("User not authorized".to_string());
    }

    Ok(AuthenticatedUser {
        user_id,
        username: user_payload
            .get("username")
            .and_then(Value::as_str)
            .map(str::to_string),
    })
}

fn check_database(config: &ApiRuntimeConfig) -> rusqlite::Result<()> {
    if let Some(parent) = config.db_path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|err| rusqlite::Error::ToSqlConversionFailure(Box::new(err)))?;
        }
    }
    let connection = Connection::open(&config.db_path)?;
    let _: i64 = connection.query_row("SELECT 1", [], |row| row.get(0))?;
    Ok(())
}

fn database_component_status(config: &ApiRuntimeConfig) -> Value {
    let started = Instant::now();
    match check_database(config) {
        Ok(()) => {
            let size_bytes = std::fs::metadata(&config.db_path)
                .map(|metadata| metadata.len())
                .unwrap_or(0);
            json!({
                "status": "healthy",
                "latency_ms": round_millis(started.elapsed()),
                "size_bytes": size_bytes,
                "size_mb": round_size_mb(size_bytes),
                "integrity_ok": true,
            })
        }
        Err(error) => json!({
            "status": "unhealthy",
            "error": error.to_string(),
            "latency_ms": round_millis(started.elapsed()),
        }),
    }
}

fn generate_correlation_id() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    format!("api-{nanos:x}")
}

fn iso_timestamp() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

fn round_millis(duration: std::time::Duration) -> f64 {
    ((duration.as_secs_f64() * 1000.0) * 100.0).round() / 100.0
}

fn round_size_mb(size_bytes: u64) -> f64 {
    (((size_bytes as f64) / (1024.0 * 1024.0)) * 100.0).round() / 100.0
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn parse_allowed_origins() -> Vec<String> {
    let configured = std::env::var("ALLOWED_ORIGINS").unwrap_or_default();
    let parsed: Vec<String> = configured
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .collect();
    if !parsed.is_empty() {
        return parsed;
    }
    vec![
        "http://localhost:3000".to_string(),
        "http://localhost:8080".to_string(),
        "http://127.0.0.1:3000".to_string(),
        "http://127.0.0.1:8080".to_string(),
    ]
}

fn parse_allowed_user_ids() -> HashSet<i64> {
    std::env::var("ALLOWED_USER_IDS")
        .unwrap_or_default()
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .filter_map(|value| value.parse::<i64>().ok())
        .collect()
}

fn parse_bool_env(key: &str, default: bool) -> bool {
    match std::env::var(key) {
        Ok(value) => match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default,
        },
        Err(_) => default,
    }
}

fn parse_u16_env(key: &str, default: u16) -> u16 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(default)
}

fn parse_usize_env(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(default)
}

fn parse_i64_env(key: &str, default: i64) -> i64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<i64>().ok())
        .unwrap_or(default)
}

fn parse_f64_env(key: &str, default: f64) -> f64 {
    std::env::var(key)
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .unwrap_or(default)
}

fn unix_timestamp() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs() as i64)
        .unwrap_or_default()
}

fn hex_string(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    fn test_db_path(label: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|value| value.as_nanos())
            .unwrap_or_default();
        std::env::temp_dir().join(format!("bsr-mobile-api-{label}-{nanos}.db"))
    }

    fn ensure_test_db(path: &Path) {
        let connection = Connection::open(path).expect("create sqlite db");
        let _: i64 = connection
            .query_row("SELECT 1", [], |row| row.get(0))
            .expect("probe sqlite");
    }

    fn test_config(label: &str) -> ApiRuntimeConfig {
        let db_path = test_db_path(label);
        ensure_test_db(&db_path);
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
            allowed_user_ids: HashSet::from([42]),
            api_rate_limit_window_seconds: 60,
            api_rate_limit_cooldown_multiplier: 2.0,
            api_rate_limit_default: 100,
            api_rate_limit_summaries: 200,
            api_rate_limit_requests: 10,
            api_rate_limit_search: 50,
        }
    }

    fn encode_test_jwt(secret: &str, user_id: i64, username: &str, exp: i64) -> String {
        let header = URL_SAFE_NO_PAD.encode(
            serde_json::to_vec(&json!({"alg": "HS256", "typ": "JWT"})).expect("jwt header"),
        );
        let claims = URL_SAFE_NO_PAD.encode(
            serde_json::to_vec(&json!({
                "user_id": user_id,
                "username": username,
                "exp": exp,
            }))
            .expect("jwt claims"),
        );
        let signing_input = format!("{header}.{claims}");
        let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).expect("jwt mac");
        mac.update(signing_input.as_bytes());
        let signature = URL_SAFE_NO_PAD.encode(mac.finalize().into_bytes());
        format!("{signing_input}.{signature}")
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
            "first_name": "Test",
        })
        .to_string();
        let mut pairs = vec![
            ("auth_date".to_string(), auth_date.to_string()),
            ("query_id".to_string(), "AAHb-test".to_string()),
            ("user".to_string(), user_payload),
        ];
        pairs.sort_by(|left, right| left.0.cmp(&right.0));
        let data_check_string = pairs
            .iter()
            .map(|(key, value)| format!("{key}={value}"))
            .collect::<Vec<_>>()
            .join("\n");

        let mut secret = HmacSha256::new_from_slice(b"WebAppData").expect("secret init");
        secret.update(bot_token.as_bytes());
        let secret_key = secret.finalize().into_bytes();

        let mut computed = HmacSha256::new_from_slice(&secret_key).expect("init data mac");
        computed.update(data_check_string.as_bytes());
        let hash = hex_string(&computed.finalize().into_bytes());

        let mut serializer = form_urlencoded::Serializer::new(String::new());
        for (key, value) in pairs {
            serializer.append_pair(&key, &value);
        }
        serializer.append_pair("hash", &hash);
        serializer.finish()
    }

    #[tokio::test]
    async fn openapi_json_is_served() {
        let state = build_state(test_config("openapi")).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/openapi.json")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn docs_page_references_openapi_json() {
        let state = build_state(test_config("docs")).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/docs")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        let body = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        let body_str = String::from_utf8(body.to_vec()).expect("utf8");
        assert!(body_str.contains("/openapi.json"));
    }

    #[tokio::test]
    async fn root_health_shell_includes_correlation_header() {
        let state = build_state(test_config("health")).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("X-Correlation-ID", "corr-123")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response
                .headers()
                .get("x-correlation-id")
                .and_then(|value| value.to_str().ok()),
            Some("corr-123")
        );
        assert!(response.headers().contains_key("x-ratelimit-limit"));
    }

    #[tokio::test]
    async fn web_route_serves_spa_shell() {
        let state = build_state(test_config("web")).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/web/settings")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::OK);
        let body = response
            .into_body()
            .collect()
            .await
            .expect("body")
            .to_bytes();
        let body_str = String::from_utf8(body.to_vec()).expect("utf8");
        assert!(body_str.contains("/static/web/assets/"));
    }

    #[tokio::test]
    async fn summaries_placeholder_requires_auth() {
        let state = build_state(test_config("protected")).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/v1/summaries")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn auth_placeholder_is_public_but_not_implemented() {
        let state = build_state(test_config("public-auth"))
            .await
            .expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/v1/auth/refresh")
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    }

    #[tokio::test]
    async fn protected_placeholder_accepts_valid_jwt() {
        let config = test_config("jwt");
        let jwt = encode_test_jwt(
            config.jwt_secret_key.as_deref().expect("jwt secret"),
            42,
            "tester",
            unix_timestamp() + 300,
        );
        let state = build_state(config).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/v1/summaries")
                    .header("Authorization", format!("Bearer {jwt}"))
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    }

    #[tokio::test]
    async fn protected_placeholder_accepts_valid_webapp_auth() {
        let config = test_config("webapp");
        let init_data = encode_webapp_init_data(
            config.bot_token.as_deref().expect("bot token"),
            42,
            "tester",
            unix_timestamp(),
        );
        let state = build_state(config).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/v1/summaries")
                    .header("X-Telegram-Init-Data", init_data)
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::NOT_IMPLEMENTED);
    }

    #[tokio::test]
    async fn authorization_header_takes_precedence_over_webapp_header() {
        let config = test_config("precedence");
        let init_data = encode_webapp_init_data(
            config.bot_token.as_deref().expect("bot token"),
            42,
            "tester",
            unix_timestamp(),
        );
        let state = build_state(config).await.expect("state");
        let app = build_router(state.clone()).with_state(state);
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/v1/summaries")
                    .header("Authorization", "Bearer invalid")
                    .header("X-Telegram-Init-Data", init_data)
                    .body(axum::body::Body::empty())
                    .unwrap(),
            )
            .await
            .expect("response");
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[test]
    fn route_manifest_contains_manual_and_openapi_routes() {
        let config = test_config("manifest");
        let raw = std::fs::read_to_string(&config.openapi_yaml_path).expect("openapi yaml");
        let yaml_value: serde_yaml::Value = serde_yaml::from_str(&raw).expect("yaml");
        let json_value = serde_json::to_value(yaml_value).expect("json");
        let manifest = build_route_manifest(&json_value);
        assert!(manifest
            .iter()
            .any(|route| route.path == "/v1/auth/refresh"));
        assert!(manifest.iter().any(|route| route.path == "/web"));
        assert!(manifest.iter().any(|route| route.path == "/health"));
    }
}
