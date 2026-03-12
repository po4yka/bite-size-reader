use std::collections::VecDeque;
use std::time::{Duration, Instant};

use bsr_summary_contract::validate_and_shape_summary;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use thiserror::Error;

const OPENROUTER_DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const OPENROUTER_DEFAULT_MODEL: &str = "deepseek/deepseek-v3.2";
const OPENROUTER_DEFAULT_REFERER: &str = "https://github.com/your-repo";
const OPENROUTER_DEFAULT_TITLE: &str = "Bite-Size Reader Bot";
const OPENROUTER_ENDPOINT: &str = "/api/v1/chat/completions";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkerRequestConfig {
    pub preset_name: Option<String>,
    pub messages: Vec<Value>,
    pub response_format: Value,
    pub max_tokens: Option<i64>,
    pub temperature: Option<f64>,
    pub top_p: Option<f64>,
    pub model_override: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkerExecutionInput {
    pub request_id: Option<i64>,
    pub requests: Vec<WorkerRequestConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkerLlmCallResult {
    pub status: String,
    pub model: Option<String>,
    pub response_text: Option<String>,
    pub response_json: Option<Value>,
    pub openrouter_response_text: Option<String>,
    pub openrouter_response_json: Option<Value>,
    pub tokens_prompt: Option<i64>,
    pub tokens_completion: Option<i64>,
    pub cost_usd: Option<f64>,
    pub latency_ms: Option<i64>,
    pub error_text: Option<String>,
    pub request_headers: Option<Value>,
    pub request_messages: Option<Vec<Value>>,
    pub endpoint: String,
    pub structured_output_used: bool,
    pub structured_output_mode: Option<String>,
    pub error_context: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkerAttemptOutput {
    pub preset_name: Option<String>,
    pub model_override: Option<String>,
    pub llm_result: WorkerLlmCallResult,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct WorkerExecutionOutput {
    pub status: String,
    pub summary: Option<Value>,
    pub attempts: Vec<WorkerAttemptOutput>,
    pub terminal_attempt_index: Option<usize>,
    pub error_text: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorkerSurface {
    UrlSinglePass,
    ForwardText,
}

impl WorkerSurface {
    fn as_str(&self) -> &'static str {
        match self {
            Self::UrlSinglePass => "url_single_pass",
            Self::ForwardText => "forward_text",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OpenRouterRuntimeConfig {
    pub api_key: String,
    pub model: String,
    pub base_url: String,
    pub http_referer: String,
    pub x_title: String,
    pub provider_order: Vec<String>,
    pub timeout: Duration,
}

impl OpenRouterRuntimeConfig {
    pub fn from_env() -> Result<Self, WorkerError> {
        let api_key =
            std::env::var("OPENROUTER_API_KEY").map_err(|_| WorkerError::MissingApiKey)?;
        let model = std::env::var("OPENROUTER_MODEL")
            .unwrap_or_else(|_| OPENROUTER_DEFAULT_MODEL.to_string());
        let base_url = std::env::var("OPENROUTER_API_BASE_URL")
            .unwrap_or_else(|_| OPENROUTER_DEFAULT_BASE_URL.to_string());
        let http_referer = std::env::var("OPENROUTER_HTTP_REFERER")
            .unwrap_or_else(|_| OPENROUTER_DEFAULT_REFERER.to_string());
        let x_title = std::env::var("OPENROUTER_X_TITLE")
            .unwrap_or_else(|_| OPENROUTER_DEFAULT_TITLE.to_string());
        let provider_order = std::env::var("OPENROUTER_PROVIDER_ORDER")
            .ok()
            .map(|raw| {
                raw.split(',')
                    .map(str::trim)
                    .filter(|value| !value.is_empty())
                    .map(ToOwned::to_owned)
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        let timeout_sec = std::env::var("REQUEST_TIMEOUT_SEC")
            .ok()
            .and_then(|raw| raw.trim().parse::<u64>().ok())
            .unwrap_or(60);

        Ok(Self {
            api_key,
            model,
            base_url: base_url.trim_end_matches('/').to_string(),
            http_referer,
            x_title,
            provider_order,
            timeout: Duration::from_secs(timeout_sec.max(1)),
        })
    }
}

#[derive(Debug, Error)]
pub enum WorkerError {
    #[error("OPENROUTER_API_KEY is required for bsr-worker")]
    MissingApiKey,
    #[error("worker request list must not be empty")]
    EmptyRequests,
    #[error("failed to build OpenRouter client: {0}")]
    HttpClientBuild(String),
    #[error("OpenRouter request failed: {0}")]
    HttpRequest(String),
    #[error("failed to parse OpenRouter response JSON: {0}")]
    ResponseJson(String),
}

pub async fn execute_url_single_pass(
    input: &WorkerExecutionInput,
    config: &OpenRouterRuntimeConfig,
) -> Result<WorkerExecutionOutput, WorkerError> {
    execute_surface(WorkerSurface::UrlSinglePass, input, config).await
}

pub async fn execute_forward_text(
    input: &WorkerExecutionInput,
    config: &OpenRouterRuntimeConfig,
) -> Result<WorkerExecutionOutput, WorkerError> {
    execute_surface(WorkerSurface::ForwardText, input, config).await
}

async fn execute_surface(
    surface: WorkerSurface,
    input: &WorkerExecutionInput,
    config: &OpenRouterRuntimeConfig,
) -> Result<WorkerExecutionOutput, WorkerError> {
    if input.requests.is_empty() {
        return Err(WorkerError::EmptyRequests);
    }

    let client = Client::builder()
        .timeout(config.timeout)
        .build()
        .map_err(|err| WorkerError::HttpClientBuild(err.to_string()))?;

    let mut attempts = Vec::with_capacity(input.requests.len());
    let mut last_error_text = None;

    for (index, request) in input.requests.iter().enumerate() {
        let attempt = execute_attempt(&client, config, input.request_id, request).await;
        let terminal_result = attempt.llm_result.clone();
        let summary = if terminal_result.status == "ok" {
            extract_shaped_summary(
                terminal_result.response_json.as_ref(),
                terminal_result.response_text.as_deref(),
            )
        } else {
            None
        };

        let llm_result = if let Some(validation_error) = summary_validation_error(&summary) {
            last_error_text = Some(validation_error.clone());
            WorkerLlmCallResult {
                status: "error".to_string(),
                error_text: Some(validation_error.clone()),
                error_context: Some(json!({
                    "status_code": Value::Null,
                    "message": validation_error,
                    "surface": surface.as_str(),
                })),
                ..terminal_result
            }
        } else {
            if let Some(summary_value) = summary.clone() {
                attempts.push(WorkerAttemptOutput {
                    preset_name: request.preset_name.clone(),
                    model_override: request.model_override.clone(),
                    llm_result: terminal_result,
                });

                return Ok(WorkerExecutionOutput {
                    status: "ok".to_string(),
                    summary: Some(summary_value),
                    attempts,
                    terminal_attempt_index: Some(index),
                    error_text: None,
                });
            }

            if terminal_result.status != "ok" {
                last_error_text = terminal_result.error_text.clone();
            } else {
                last_error_text = Some("summary_parse_failed".to_string());
            }

            WorkerLlmCallResult {
                status: "error".to_string(),
                error_text: Some(
                    last_error_text
                        .clone()
                        .unwrap_or_else(|| "summary_parse_failed".to_string()),
                ),
                error_context: Some(json!({
                    "status_code": Value::Null,
                    "message": last_error_text
                        .clone()
                        .unwrap_or_else(|| "summary_parse_failed".to_string()),
                    "surface": surface.as_str(),
                })),
                ..terminal_result
            }
        };

        attempts.push(WorkerAttemptOutput {
            preset_name: request.preset_name.clone(),
            model_override: request.model_override.clone(),
            llm_result,
        });
    }

    Ok(WorkerExecutionOutput {
        status: "error".to_string(),
        summary: None,
        terminal_attempt_index: attempts.len().checked_sub(1),
        error_text: last_error_text,
        attempts,
    })
}

async fn execute_attempt(
    client: &Client,
    config: &OpenRouterRuntimeConfig,
    request_id: Option<i64>,
    request: &WorkerRequestConfig,
) -> WorkerAttemptOutput {
    let model = request
        .model_override
        .clone()
        .unwrap_or_else(|| config.model.clone());
    let structured_output_mode = request
        .response_format
        .get("type")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);
    let structured_output_used = !request.response_format.is_null();
    let request_headers = build_redacted_headers(config);
    let request_messages = request.messages.clone();
    let endpoint = format!("{}{}", config.base_url, OPENROUTER_ENDPOINT);
    let mut body = json!({
        "model": model,
        "messages": request.messages,
        "temperature": request.temperature.unwrap_or(0.2),
    });

    if let Some(max_tokens) = request.max_tokens {
        body["max_tokens"] = json!(max_tokens);
    }
    if let Some(top_p) = request.top_p {
        body["top_p"] = json!(top_p);
    }
    if !request.response_format.is_null() {
        body["response_format"] = request.response_format.clone();
    }
    if !config.provider_order.is_empty() {
        body["provider"] = json!({ "order": config.provider_order });
    }

    let started = Instant::now();
    let response = client
        .post(endpoint.clone())
        .headers(build_http_headers(config))
        .json(&body)
        .send()
        .await;
    let latency_ms = started.elapsed().as_millis() as i64;

    let llm_result = match response {
        Ok(response) => {
            build_llm_result_from_response(
                response,
                latency_ms,
                request_headers.clone(),
                request_messages.clone(),
                structured_output_used,
                structured_output_mode.clone(),
                request_id,
            )
            .await
        }
        Err(err) => WorkerLlmCallResult {
            status: "error".to_string(),
            model: Some(model.clone()),
            response_text: None,
            response_json: None,
            openrouter_response_text: None,
            openrouter_response_json: None,
            tokens_prompt: None,
            tokens_completion: None,
            cost_usd: None,
            latency_ms: Some(latency_ms),
            error_text: Some(format!("network_error: {err}")),
            request_headers: Some(request_headers.clone()),
            request_messages: Some(request_messages.clone()),
            endpoint: OPENROUTER_ENDPOINT.to_string(),
            structured_output_used,
            structured_output_mode,
            error_context: Some(json!({
                "status_code": Value::Null,
                "message": "network_error",
                "api_error": err.to_string(),
                "request_id": request_id,
            })),
        },
    };

    WorkerAttemptOutput {
        preset_name: request.preset_name.clone(),
        model_override: request.model_override.clone(),
        llm_result,
    }
}

async fn build_llm_result_from_response(
    response: reqwest::Response,
    latency_ms: i64,
    request_headers: Value,
    request_messages: Vec<Value>,
    structured_output_used: bool,
    structured_output_mode: Option<String>,
    request_id: Option<i64>,
) -> WorkerLlmCallResult {
    let status = response.status();
    let body_bytes = match response.bytes().await {
        Ok(bytes) => bytes,
        Err(err) => {
            return WorkerLlmCallResult {
                status: "error".to_string(),
                model: None,
                response_text: None,
                response_json: None,
                openrouter_response_text: None,
                openrouter_response_json: None,
                tokens_prompt: None,
                tokens_completion: None,
                cost_usd: None,
                latency_ms: Some(latency_ms),
                error_text: Some(format!("response_read_failed: {err}")),
                request_headers: Some(request_headers),
                request_messages: Some(request_messages),
                endpoint: OPENROUTER_ENDPOINT.to_string(),
                structured_output_used,
                structured_output_mode,
                error_context: Some(json!({
                    "status_code": Value::Null,
                    "message": "response_read_failed",
                    "api_error": err.to_string(),
                    "request_id": request_id,
                })),
            };
        }
    };

    let body_text = String::from_utf8_lossy(&body_bytes).to_string();
    let response_json = serde_json::from_slice::<Value>(&body_bytes).ok();
    let model = response_json
        .as_ref()
        .and_then(|payload| payload.get("model"))
        .and_then(Value::as_str)
        .map(ToOwned::to_owned);
    let response_text = response_json
        .as_ref()
        .and_then(extract_response_text)
        .or_else(|| (!body_text.trim().is_empty()).then_some(body_text.clone()));
    let tokens_prompt = response_json
        .as_ref()
        .and_then(|payload| payload.get("usage"))
        .and_then(|usage| usage.get("prompt_tokens"))
        .and_then(Value::as_i64);
    let tokens_completion = response_json
        .as_ref()
        .and_then(|payload| payload.get("usage"))
        .and_then(|usage| usage.get("completion_tokens"))
        .and_then(Value::as_i64);
    let cost_usd = response_json
        .as_ref()
        .and_then(|payload| payload.get("usage"))
        .and_then(|usage| usage.get("total_cost").or_else(|| usage.get("cost")))
        .and_then(Value::as_f64);

    if status.is_success() {
        return WorkerLlmCallResult {
            status: "ok".to_string(),
            model,
            response_text: response_text.clone(),
            response_json: response_json.clone(),
            openrouter_response_text: response_text,
            openrouter_response_json: response_json,
            tokens_prompt,
            tokens_completion,
            cost_usd,
            latency_ms: Some(latency_ms),
            error_text: None,
            request_headers: Some(request_headers),
            request_messages: Some(request_messages),
            endpoint: OPENROUTER_ENDPOINT.to_string(),
            structured_output_used,
            structured_output_mode,
            error_context: None,
        };
    }

    let api_error = response_json
        .as_ref()
        .and_then(extract_api_error)
        .unwrap_or_else(|| {
            status
                .canonical_reason()
                .unwrap_or("http_error")
                .to_string()
        });

    WorkerLlmCallResult {
        status: "error".to_string(),
        model,
        response_text: response_text.clone(),
        response_json: response_json.clone(),
        openrouter_response_text: response_text,
        openrouter_response_json: response_json,
        tokens_prompt,
        tokens_completion,
        cost_usd,
        latency_ms: Some(latency_ms),
        error_text: Some(api_error.clone()),
        request_headers: Some(request_headers),
        request_messages: Some(request_messages),
        endpoint: OPENROUTER_ENDPOINT.to_string(),
        structured_output_used,
        structured_output_mode,
        error_context: Some(json!({
            "status_code": status.as_u16(),
            "message": api_error,
            "api_error": api_error,
            "request_id": request_id,
        })),
    }
}

fn build_http_headers(config: &OpenRouterRuntimeConfig) -> HeaderMap {
    let mut headers = HeaderMap::new();
    let auth_value = HeaderValue::from_str(&format!("Bearer {}", config.api_key))
        .unwrap_or_else(|_| HeaderValue::from_static("Bearer invalid"));
    headers.insert(AUTHORIZATION, auth_value);
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    headers.insert(
        "HTTP-Referer",
        HeaderValue::from_str(&config.http_referer)
            .unwrap_or_else(|_| HeaderValue::from_static(OPENROUTER_DEFAULT_REFERER)),
    );
    headers.insert(
        "X-Title",
        HeaderValue::from_str(&config.x_title)
            .unwrap_or_else(|_| HeaderValue::from_static(OPENROUTER_DEFAULT_TITLE)),
    );
    headers
}

fn build_redacted_headers(config: &OpenRouterRuntimeConfig) -> Value {
    json!({
        "Authorization": "REDACTED",
        "Content-Type": "application/json",
        "HTTP-Referer": config.http_referer,
        "X-Title": config.x_title,
    })
}

fn extract_response_text(payload: &Value) -> Option<String> {
    let message = payload
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
        .and_then(|choice| choice.get("message"))?;

    if let Some(parsed) = message.get("parsed") {
        if parsed.is_object() || parsed.is_array() {
            return serde_json::to_string(parsed).ok();
        }
    }

    message.get("content").and_then(content_to_text)
}

fn content_to_text(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.clone()),
        Value::Array(items) => {
            let mut json_segments = Vec::new();
            let mut text_segments = Vec::new();
            for item in items {
                if let Some(object) = item.as_object() {
                    if let Some(text) = object.get("text").and_then(Value::as_str) {
                        text_segments.push(text.trim().to_string());
                    }
                    for key in ["json", "parsed", "arguments", "output"] {
                        if let Some(nested) = object.get(key) {
                            if nested.is_object() || nested.is_array() {
                                if let Ok(serialized) = serde_json::to_string(nested) {
                                    json_segments.push(serialized);
                                }
                            }
                        }
                    }
                }
            }
            if !json_segments.is_empty() {
                Some(json_segments.join("\n"))
            } else if !text_segments.is_empty() {
                Some(text_segments.join("\n"))
            } else {
                None
            }
        }
        _ => None,
    }
}

fn extract_api_error(payload: &Value) -> Option<String> {
    if let Some(error) = payload.get("error") {
        if let Some(message) = error.get("message").and_then(Value::as_str) {
            return Some(message.to_string());
        }
        if let Some(text) = error.as_str() {
            return Some(text.to_string());
        }
    }
    payload
        .get("message")
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn extract_shaped_summary(
    response_json: Option<&Value>,
    response_text: Option<&str>,
) -> Option<Value> {
    if let Some(candidate) = response_json.and_then(extract_structured_candidate) {
        if let Ok(summary) = validate_and_shape_summary(&candidate) {
            return Some(summary);
        }
    }

    let mut text_candidates = VecDeque::new();
    if let Some(text) = response_text {
        for candidate in iter_text_candidates(text) {
            text_candidates.push_back(candidate);
        }
    }

    while let Some(candidate_text) = text_candidates.pop_front() {
        let Ok(parsed) = serde_json::from_str::<Value>(&candidate_text) else {
            continue;
        };
        if parsed.is_object() {
            if let Ok(summary) = validate_and_shape_summary(&parsed) {
                return Some(summary);
            }
        }
    }

    None
}

fn summary_validation_error(summary: &Option<Value>) -> Option<String> {
    let Some(summary) = summary else {
        return None;
    };

    if summary_has_content(summary) {
        None
    } else {
        Some("summary_fields_empty".to_string())
    }
}

fn summary_has_content(summary: &Value) -> bool {
    ["tldr", "summary_250", "summary_1000"].iter().any(|field| {
        summary
            .get(*field)
            .and_then(Value::as_str)
            .map(|value| !value.trim().is_empty())
            .unwrap_or(false)
    })
}

fn extract_structured_candidate(payload: &Value) -> Option<Value> {
    if payload.is_object() && looks_like_summary_object(payload) {
        return Some(payload.clone());
    }

    payload
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
        .and_then(|choice| choice.get("message"))
        .and_then(|message| message.get("parsed"))
        .filter(|parsed| parsed.is_object())
        .cloned()
}

fn looks_like_summary_object(value: &Value) -> bool {
    [
        "summary_250",
        "summary_1000",
        "tldr",
        "summary250",
        "summary1000",
        "key_ideas",
    ]
    .iter()
    .any(|key| value.get(*key).is_some())
}

fn iter_text_candidates(response_text: &str) -> Vec<String> {
    let base = response_text.trim();
    if base.is_empty() {
        return Vec::new();
    }

    let mut seen = Vec::<String>::new();
    let mut candidates = Vec::<String>::new();
    push_candidate(&mut seen, &mut candidates, base);

    let without_fence = strip_code_fence(base);
    push_candidate(&mut seen, &mut candidates, &without_fence);

    let backtick_stripped = without_fence.trim_matches('`').trim().to_string();
    push_candidate(&mut seen, &mut candidates, &backtick_stripped);

    if let Some(brace_slice) = slice_between_braces(&backtick_stripped) {
        push_candidate(&mut seen, &mut candidates, &brace_slice);
    }

    candidates
}

fn push_candidate(seen: &mut Vec<String>, candidates: &mut Vec<String>, candidate: &str) {
    let normalized = candidate.trim();
    if normalized.is_empty() || seen.iter().any(|existing| existing == normalized) {
        return;
    }

    seen.push(normalized.to_string());
    candidates.push(normalized.to_string());
}

fn strip_code_fence(text: &str) -> String {
    let stripped = text.trim();
    if !stripped.starts_with("```") {
        return stripped.to_string();
    }

    let mut lines: Vec<&str> = stripped.lines().collect();
    if lines
        .first()
        .map(|line| line.trim_start().starts_with("```"))
        == Some(true)
    {
        lines.remove(0);
    }
    if lines.last().map(|line| line.trim().starts_with("```")) == Some(true) {
        lines.pop();
    }
    lines.join("\n").trim().to_string()
}

fn slice_between_braces(text: &str) -> Option<String> {
    let start = text.find('{')?;
    let end = text.rfind('}')?;
    (end > start).then(|| text[start..=end].to_string())
}

#[cfg(test)]
mod tests {
    use std::collections::VecDeque;
    use std::net::SocketAddr;
    use std::sync::{Arc, Mutex};

    use axum::extract::State;
    use axum::http::StatusCode;
    use axum::response::IntoResponse;
    use axum::routing::post;
    use axum::{Json, Router};
    use serde_json::json;
    use tokio::net::TcpListener;

    use super::*;

    #[derive(Clone)]
    struct MockState {
        responses: Arc<Mutex<VecDeque<(StatusCode, Value)>>>,
    }

    async fn mock_handler(
        State(state): State<MockState>,
        Json(_payload): Json<Value>,
    ) -> impl IntoResponse {
        let mut guard = state.responses.lock().expect("mock state lock");
        let (status, body) = guard
            .pop_front()
            .expect("mock response should exist for each request");
        (status, Json(body))
    }

    async fn start_server(responses: Vec<(StatusCode, Value)>) -> SocketAddr {
        let listener = TcpListener::bind("127.0.0.1:0")
            .await
            .expect("listener should bind");
        let addr = listener.local_addr().expect("listener address");
        let state = MockState {
            responses: Arc::new(Mutex::new(VecDeque::from(responses))),
        };
        let app = Router::new()
            .route("/api/v1/chat/completions", post(mock_handler))
            .with_state(state);
        tokio::spawn(async move {
            axum::serve(listener, app)
                .await
                .expect("mock server should run");
        });
        addr
    }

    fn worker_config(base_url: String) -> OpenRouterRuntimeConfig {
        OpenRouterRuntimeConfig {
            api_key: "test-key".to_string(),
            model: "primary-model".to_string(),
            base_url,
            http_referer: "https://example.test".to_string(),
            x_title: "Test Worker".to_string(),
            provider_order: vec!["test-provider".to_string()],
            timeout: Duration::from_secs(5),
        }
    }

    fn summary_request() -> WorkerRequestConfig {
        WorkerRequestConfig {
            preset_name: Some("schema_strict".to_string()),
            messages: vec![
                json!({"role": "system", "content": "system"}),
                json!({"role": "user", "content": "user"}),
            ],
            response_format: json!({"type": "json_object"}),
            max_tokens: Some(4096),
            temperature: Some(0.2),
            top_p: Some(0.9),
            model_override: Some("primary-model".to_string()),
        }
    }

    #[tokio::test]
    async fn executes_summary_on_first_attempt() {
        let summary_payload = json!({
            "summary_250": "Short summary.",
            "summary_1000": "Longer summary.",
            "tldr": "TLDR."
        });
        let addr = start_server(vec![(
            StatusCode::OK,
            json!({
                "model": "primary-model",
                "choices": [{"message": {"parsed": summary_payload}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 34,
                    "total_cost": 0.12
                }
            }),
        )])
        .await;

        let output = execute_url_single_pass(
            &WorkerExecutionInput {
                request_id: Some(42),
                requests: vec![summary_request()],
            },
            &worker_config(format!("http://{addr}")),
        )
        .await
        .expect("worker execution should succeed");

        assert_eq!(output.status, "ok");
        assert_eq!(output.terminal_attempt_index, Some(0));
        assert_eq!(output.attempts.len(), 1);
        assert_eq!(
            output
                .summary
                .as_ref()
                .and_then(|summary| summary.get("summary_250")),
            Some(&json!("Short summary."))
        );
    }

    #[tokio::test]
    async fn retries_next_request_after_parse_failure() {
        let summary_payload = json!({
            "summary_250": "Short summary.",
            "summary_1000": "Longer summary.",
            "tldr": "TLDR."
        });
        let addr = start_server(vec![
            (
                StatusCode::OK,
                json!({
                    "model": "primary-model",
                    "choices": [{"message": {"content": "not-json"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2}
                }),
            ),
            (
                StatusCode::OK,
                json!({
                    "model": "fallback-model",
                    "choices": [{"message": {"parsed": summary_payload}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4}
                }),
            ),
        ])
        .await;

        let mut fallback_request = summary_request();
        fallback_request.preset_name = Some("json_object_fallback".to_string());
        fallback_request.model_override = Some("fallback-model".to_string());

        let output = execute_forward_text(
            &WorkerExecutionInput {
                request_id: Some(77),
                requests: vec![summary_request(), fallback_request],
            },
            &worker_config(format!("http://{addr}")),
        )
        .await
        .expect("worker execution should succeed");

        assert_eq!(output.status, "ok");
        assert_eq!(output.terminal_attempt_index, Some(1));
        assert_eq!(output.attempts.len(), 2);
        assert_eq!(
            output.attempts[0].llm_result.error_text.as_deref(),
            Some("summary_parse_failed")
        );
        assert_eq!(
            output
                .summary
                .as_ref()
                .and_then(|summary| summary.get("summary_250")),
            Some(&json!("Short summary."))
        );
    }
}
