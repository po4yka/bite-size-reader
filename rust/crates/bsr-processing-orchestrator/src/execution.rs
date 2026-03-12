use std::env;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::Duration;

use bsr_persistence::{
    create_minimal_request, create_request, get_request_by_forward, get_summary_by_request,
    insert_crawl_result, insert_llm_call, open_connection, update_request_correlation_id,
    update_request_error, update_request_lang_detected, update_request_status, upsert_summary,
    CreateRequestInput, InsertCrawlResultInput, InsertLlmCallInput, MinimalRequestInput,
    RequestErrorUpdate, UpsertSummaryInput,
};
use bsr_summary_contract::validate_and_shape_summary;
use bsr_worker::{
    execute_chunked_url, execute_forward_text, execute_url_single_pass, ChunkedUrlExecutionInput,
    OpenRouterRuntimeConfig, WorkerAttemptOutput, WorkerChunkedSynthesisConfig,
    WorkerExecutionInput, WorkerExecutionOutput, WorkerLlmCallResult, WorkerRequestConfig,
};
use redis::Commands;
use regex::Regex;
use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use reqwest::Client;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use thiserror::Error;
use url::Url;

use crate::{
    build_forward_processing_plan, build_url_processing_plan, ForwardProcessingPlanInput,
    UrlProcessingPlanInput, LANG_EN, LANG_RU,
};

const DEFAULT_DB_PATH: &str = "/data/app.db";
const FIRECRAWL_BASE_URL: &str = "https://api.firecrawl.dev";
const FIRECRAWL_SCRAPE_ENDPOINT: &str = "/v2/scrape";
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UrlExecuteInput {
    #[serde(default)]
    pub existing_request_id: Option<i64>,
    pub correlation_id: Option<String>,
    pub db_path: Option<String>,
    pub input_url: String,
    pub chat_id: Option<i64>,
    pub user_id: Option<i64>,
    pub input_message_id: Option<i64>,
    pub silent: bool,
    pub preferred_language: String,
    pub route_version: i64,
    pub prompt_version: String,
    pub enable_chunking: bool,
    pub configured_chunk_max_chars: usize,
    pub primary_model: String,
    pub long_context_model: Option<String>,
    pub fallback_models: Vec<String>,
    pub flash_model: Option<String>,
    pub flash_fallback_models: Vec<String>,
    pub structured_output_mode: String,
    pub temperature: f64,
    pub top_p: Option<f64>,
    pub json_temperature: Option<f64>,
    pub json_top_p: Option<f64>,
    pub vision_model: Option<String>,
    pub enable_two_pass_enrichment: bool,
    pub web_search_context: Option<String>,
    #[serde(default)]
    pub persist_is_read: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ForwardExecuteInput {
    #[serde(default)]
    pub existing_request_id: Option<i64>,
    pub correlation_id: Option<String>,
    pub db_path: Option<String>,
    pub text: String,
    pub chat_id: Option<i64>,
    pub user_id: Option<i64>,
    pub input_message_id: Option<i64>,
    pub fwd_from_chat_id: Option<i64>,
    pub fwd_from_msg_id: Option<i64>,
    pub source_chat_title: Option<String>,
    pub source_user_first_name: Option<String>,
    pub source_user_last_name: Option<String>,
    pub forward_sender_name: Option<String>,
    pub preferred_language: String,
    pub route_version: i64,
    pub primary_model: String,
    pub fallback_models: Vec<String>,
    pub flash_model: Option<String>,
    pub flash_fallback_models: Vec<String>,
    pub structured_output_mode: String,
    pub temperature: f64,
    pub top_p: Option<f64>,
    pub json_temperature: Option<f64>,
    pub json_top_p: Option<f64>,
    pub enable_two_pass_enrichment: bool,
    pub normalize_forward_prompt: bool,
    pub prompt_version: String,
    #[serde(default)]
    pub persist_is_read: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProcessingTerminalResult {
    pub status: String,
    pub request_id: Option<i64>,
    pub summary_id: Option<i64>,
    pub summary: Option<Value>,
    pub title: Option<String>,
    pub detected_language: Option<String>,
    pub chosen_lang: Option<String>,
    pub needs_ru_translation: bool,
    pub cached: bool,
    pub model: Option<String>,
    pub chunk_count: Option<usize>,
    pub error_code: Option<String>,
    pub error_text: Option<String>,
    pub dedupe_hash: Option<String>,
    pub content_text: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "event_type", rename_all = "snake_case")]
pub enum OrchestratorEvent {
    Phase {
        phase: String,
        request_id: Option<i64>,
        model: Option<String>,
        title: Option<String>,
        content_length: Option<usize>,
        detail: Option<String>,
    },
    DraftDelta {
        request_id: Option<i64>,
        field: Option<String>,
        delta: String,
    },
    Attempt {
        request_id: Option<i64>,
        attempt_index: usize,
        preset_name: Option<String>,
        model_override: Option<String>,
        llm_result: WorkerLlmCallResult,
    },
    Result {
        payload: ProcessingTerminalResult,
    },
}

#[derive(Debug, Error)]
pub enum ExecutionError {
    #[error("persistence error: {0}")]
    Persistence(#[from] bsr_persistence::PersistenceError),
    #[error("worker error: {0}")]
    Worker(#[from] bsr_worker::WorkerError),
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("redis error: {0}")]
    Redis(#[from] redis::RedisError),
    #[error("prompt root not found from {0}")]
    PromptRootNotFound(String),
    #[error("invalid firecrawl authorization header")]
    InvalidFirecrawlHeader,
    #[error("invalid input: {0}")]
    InvalidInput(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct FirecrawlRuntimeConfig {
    api_key: Option<String>,
    base_url: String,
    timeout: Duration,
    wait_for_ms: i64,
    max_age_seconds: i64,
    include_markdown: bool,
    include_html: bool,
    include_images: bool,
    block_ads: bool,
    remove_base64_images: bool,
    skip_tls_verification: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
struct FirecrawlResult {
    status: String,
    http_status: Option<i64>,
    content_markdown: Option<String>,
    content_html: Option<String>,
    structured_json: Option<Value>,
    metadata_json: Option<Value>,
    links_json: Option<Value>,
    response_success: Option<bool>,
    response_error_code: Option<String>,
    response_error_message: Option<String>,
    response_details: Option<Value>,
    latency_ms: Option<i64>,
    error_text: Option<String>,
    source_url: Option<String>,
    endpoint: Option<String>,
    options_json: Option<Value>,
    correlation_id: Option<String>,
}

pub async fn execute_url_flow<F>(
    input: &UrlExecuteInput,
    emit: &mut F,
) -> Result<ProcessingTerminalResult, ExecutionError>
where
    F: FnMut(OrchestratorEvent) -> Result<(), ExecutionError>,
{
    let normalized_url = normalize_url(&input.input_url)?;
    let dedupe_hash = url_hash_sha256(&normalized_url);
    let db_path = resolve_db_path(input.db_path.as_deref());
    let connection = open_connection(db_path)?;

    let request = if let Some(existing_request_id) = input.existing_request_id {
        let request = bsr_persistence::get_request_by_id(&connection, existing_request_id)?
            .ok_or_else(|| {
                ExecutionError::InvalidInput("existing request not found".to_string())
            })?;
        if let Some(correlation_id) = input.correlation_id.as_deref() {
            update_request_correlation_id(&connection, request.id, correlation_id)?;
        }
        request
    } else {
        let minimal_request = create_minimal_request(
            &connection,
            &MinimalRequestInput {
                request_type: "url".to_string(),
                status: "pending".to_string(),
                correlation_id: input.correlation_id.clone(),
                chat_id: input.chat_id,
                user_id: input.user_id,
                input_url: Some(input.input_url.clone()),
                normalized_url: Some(normalized_url.clone()),
                dedupe_hash: Some(dedupe_hash.clone()),
            },
        )?;
        minimal_request.0
    };

    emit(OrchestratorEvent::Phase {
        phase: "cache_lookup".to_string(),
        request_id: Some(request.id),
        model: None,
        title: None,
        content_length: None,
        detail: Some("dedupe_lookup".to_string()),
    })?;

    if let Some(cached_summary) = get_summary_by_request(&connection, request.id)? {
        if let Some(summary_payload) = cached_summary.json_payload.clone() {
            if let Some(correlation_id) = input.correlation_id.as_deref() {
                update_request_correlation_id(&connection, request.id, correlation_id)?;
            }
            let result = ProcessingTerminalResult {
                status: "cached".to_string(),
                request_id: Some(request.id),
                summary_id: Some(cached_summary.id),
                summary: Some(summary_payload.clone()),
                title: summary_title(&summary_payload),
                detected_language: request.lang_detected.clone(),
                chosen_lang: request.lang_detected.clone(),
                needs_ru_translation: false,
                cached: true,
                model: None,
                chunk_count: None,
                error_code: None,
                error_text: None,
                dedupe_hash: Some(dedupe_hash),
                content_text: None,
            };
            emit(OrchestratorEvent::Phase {
                phase: "completed".to_string(),
                request_id: Some(request.id),
                model: None,
                title: result.title.clone(),
                content_length: None,
                detail: Some("sqlite_cache_hit".to_string()),
            })?;
            emit(OrchestratorEvent::Result {
                payload: result.clone(),
            })?;
            return Ok(result);
        }
    }

    update_request_status(&connection, request.id, "extracting")?;
    emit(OrchestratorEvent::Phase {
        phase: "extracting".to_string(),
        request_id: Some(request.id),
        model: None,
        title: None,
        content_length: None,
        detail: Some(normalized_url.clone()),
    })?;

    let firecrawl_cfg = FirecrawlRuntimeConfig::from_env();
    let firecrawl_result = scrape_url(
        &firecrawl_cfg,
        &normalized_url,
        input.correlation_id.as_deref(),
    )
    .await?;
    let crawl_record = insert_crawl_result(
        &connection,
        &InsertCrawlResultInput {
            request_id: request.id,
            firecrawl_success: firecrawl_result
                .response_success
                .unwrap_or_else(|| firecrawl_result.status == "success"),
            source_url: Some(normalized_url.clone()),
            endpoint: firecrawl_result.endpoint.clone(),
            http_status: firecrawl_result.http_status,
            status: Some(firecrawl_result.status.clone()),
            options_json: firecrawl_result.options_json.clone(),
            correlation_id: input.correlation_id.clone(),
            content_markdown: firecrawl_result.content_markdown.clone(),
            content_html: firecrawl_result.content_html.clone(),
            structured_json: firecrawl_result.structured_json.clone(),
            metadata_json: firecrawl_result.metadata_json.clone(),
            links_json: firecrawl_result.links_json.clone(),
            firecrawl_error_code: firecrawl_result.response_error_code.clone(),
            firecrawl_error_message: firecrawl_result.response_error_message.clone(),
            firecrawl_details_json: firecrawl_result.response_details.clone(),
            raw_response_json: None,
            latency_ms: firecrawl_result.latency_ms,
            error_text: firecrawl_result.error_text.clone(),
        },
    )?;

    if let Some(low_value) = detect_low_value_content(&firecrawl_result) {
        let result = fail_request(
            &connection,
            request.id,
            "FIRECRAWL_LOW_VALUE",
            &format!(
                "Low-value content detected: {}",
                low_value
                    .get("reason")
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
            ),
            json!({
                "stage": "extraction",
                "component": "firecrawl",
                "reason_code": "FIRECRAWL_LOW_VALUE",
                "quality_reason": low_value.get("reason").cloned().unwrap_or(Value::Null),
                "content_signals": low_value.get("metrics").cloned().unwrap_or(Value::Null),
                "source_url": normalized_url,
            }),
        )?;
        emit(OrchestratorEvent::Phase {
            phase: "failed".to_string(),
            request_id: Some(request.id),
            model: None,
            title: None,
            content_length: None,
            detail: result.error_text.clone(),
        })?;
        emit(OrchestratorEvent::Result {
            payload: result.clone(),
        })?;
        return Ok(result);
    }

    let extracted = extract_content_text(&firecrawl_result);
    if extracted.content_text.trim().is_empty() || firecrawl_result.status != "success" {
        let error_text = firecrawl_result
            .error_text
            .clone()
            .or_else(|| firecrawl_result.response_error_message.clone())
            .unwrap_or_else(|| "Content extraction failed".to_string());
        let result = fail_request(
            &connection,
            request.id,
            "FIRECRAWL_ERROR",
            &error_text,
            json!({
                "stage": "extraction",
                "component": "firecrawl",
                "reason_code": "FIRECRAWL_ERROR",
                "http_status": firecrawl_result.http_status,
                "provider_error_code": firecrawl_result.response_error_code,
                "latency_ms": firecrawl_result.latency_ms,
                "source_url": normalized_url,
            }),
        )?;
        emit(OrchestratorEvent::Phase {
            phase: "failed".to_string(),
            request_id: Some(request.id),
            model: None,
            title: None,
            content_length: None,
            detail: result.error_text.clone(),
        })?;
        emit(OrchestratorEvent::Result {
            payload: result.clone(),
        })?;
        return Ok(result);
    }

    let detected_language = detect_language(&extracted.content_text);
    update_request_lang_detected(&connection, request.id, &detected_language)?;
    let chosen_lang = crate::choose_language(&input.preferred_language, &detected_language);
    let needs_ru_translation =
        !input.silent && chosen_lang.as_str() != LANG_RU && detected_language.as_str() != LANG_RU;

    let plan = build_url_processing_plan(&UrlProcessingPlanInput {
        dedupe_hash: dedupe_hash.clone(),
        content_text: extracted.content_text.clone(),
        detected_language: detected_language.clone(),
        preferred_language: input.preferred_language.clone(),
        silent: input.silent,
        enable_chunking: input.enable_chunking,
        configured_chunk_max_chars: input.configured_chunk_max_chars.max(1),
        primary_model: input.primary_model.clone(),
        long_context_model: input.long_context_model.clone(),
        schema_response_type: input.structured_output_mode.clone(),
        json_object_response_type: "json_object".to_string(),
        max_tokens_schema: None,
        max_tokens_json_object: None,
        base_temperature: Some(input.temperature),
        base_top_p: input.top_p,
        json_temperature: input.json_temperature,
        json_top_p: input.json_top_p,
        fallback_models: input.fallback_models.clone(),
        flash_model: input.flash_model.clone(),
        flash_fallback_models: input.flash_fallback_models.clone(),
    });

    let (content_for_summary, base_model) = prepare_summary_content(
        &extracted.content_text,
        plan.effective_max_chars,
        input.long_context_model.as_deref(),
        input.vision_model.as_deref(),
        !extracted.images.is_empty(),
        &input.primary_model,
    );
    let search_context = input.web_search_context.clone().unwrap_or_default();

    if let Some(redis_summary) = read_summary_cache(
        &dedupe_hash,
        &input.prompt_version,
        &chosen_lang,
        &base_model,
    )? {
        emit(OrchestratorEvent::Phase {
            phase: "persisting".to_string(),
            request_id: Some(request.id),
            model: Some(base_model.clone()),
            title: extracted.title.clone(),
            content_length: Some(extracted.content_text.len()),
            detail: Some("redis_cache_hit".to_string()),
        })?;

        let shaped_summary = ensure_summary_metadata(
            redis_summary,
            extracted.title.as_deref(),
            Some(&normalized_url),
            crawl_record.metadata_json.as_ref(),
        );
        let persisted = upsert_summary(
            &connection,
            &UpsertSummaryInput {
                request_id: request.id,
                lang: chosen_lang.clone(),
                json_payload: shaped_summary.clone(),
                insights_json: None,
                is_read: !input.silent,
            },
        )?;
        update_request_status(&connection, request.id, "ok")?;

        let result = ProcessingTerminalResult {
            status: "cached".to_string(),
            request_id: Some(request.id),
            summary_id: Some(persisted.id),
            summary: Some(shaped_summary.clone()),
            title: extracted
                .title
                .clone()
                .or_else(|| summary_title(&shaped_summary)),
            detected_language: Some(detected_language),
            chosen_lang: Some(chosen_lang),
            needs_ru_translation,
            cached: true,
            model: Some(base_model),
            chunk_count: plan.chunk_plan.as_ref().map(|plan| plan.chunks.len()),
            error_code: None,
            error_text: None,
            dedupe_hash: Some(dedupe_hash),
            content_text: Some(extracted.content_text),
        };
        emit_draft_delta(emit, request.id, result.summary.as_ref())?;
        emit(OrchestratorEvent::Phase {
            phase: "completed".to_string(),
            request_id: Some(request.id),
            model: result.model.clone(),
            title: result.title.clone(),
            content_length: result.content_text.as_ref().map(String::len),
            detail: Some("redis_cache_hit".to_string()),
        })?;
        emit(OrchestratorEvent::Result {
            payload: result.clone(),
        })?;
        return Ok(result);
    }

    emit(OrchestratorEvent::Phase {
        phase: "summarizing".to_string(),
        request_id: Some(request.id),
        model: Some(base_model.clone()),
        title: extracted.title.clone(),
        content_length: Some(content_for_summary.len()),
        detail: Some(plan.summary_strategy.clone()),
    })?;

    let worker_config = OpenRouterRuntimeConfig::from_env()?;
    let (worker_output, chunk_count) = if plan.summary_strategy == "chunked" {
        execute_chunked_flow(
            &worker_config,
            &plan,
            &UrlWorkerSettings {
                system_prompt: load_summary_prompt(&chosen_lang)?,
                chosen_lang: chosen_lang.clone(),
                structured_output_mode: input.structured_output_mode.clone(),
                temperature: input.temperature,
                top_p: input.top_p,
                json_temperature: input.json_temperature,
                json_top_p: input.json_top_p,
                primary_model: base_model.clone(),
            },
            request.id,
        )
        .await?
    } else {
        let system_prompt = load_summary_prompt(&chosen_lang)?;
        let messages = build_summary_messages(
            &system_prompt,
            &build_summary_user_content(&content_for_summary, &chosen_lang, &search_context),
            &extracted.images,
        );
        let output = execute_url_single_pass(
            &WorkerExecutionInput {
                request_id: Some(request.id),
                requests: build_summary_requests(
                    &messages,
                    &base_model,
                    &input.structured_output_mode,
                    &input.fallback_models,
                    input.flash_model.as_deref(),
                    &input.flash_fallback_models,
                    input.temperature,
                    input.top_p,
                    input.json_temperature,
                    input.json_top_p,
                    &content_for_summary,
                    &build_summary_user_content(
                        &content_for_summary,
                        &chosen_lang,
                        &search_context,
                    ),
                ),
            },
            &worker_config,
        )
        .await?;
        (output, None)
    };

    persist_attempts(&connection, request.id, &worker_output.attempts, emit)?;

    if worker_output.status != "ok" {
        let result = fail_request(
            &connection,
            request.id,
            "LLM_SUMMARY_FAILED",
            worker_output
                .error_text
                .as_deref()
                .unwrap_or("Summary generation failed"),
            json!({
                "stage": "summarizing",
                "component": "openrouter",
                "reason_code": "LLM_SUMMARY_FAILED",
                "request_id": request.id,
            }),
        )?;
        emit(OrchestratorEvent::Phase {
            phase: "failed".to_string(),
            request_id: Some(request.id),
            model: Some(base_model),
            title: extracted.title.clone(),
            content_length: Some(content_for_summary.len()),
            detail: result.error_text.clone(),
        })?;
        emit(OrchestratorEvent::Result {
            payload: result.clone(),
        })?;
        return Ok(result);
    }

    let terminal_model_name = terminal_model(&worker_output).or_else(|| Some(base_model.clone()));
    let mut summary = worker_output.summary.clone().unwrap_or_else(|| json!({}));
    summary = ensure_summary_metadata(
        summary,
        extracted.title.as_deref(),
        Some(&normalized_url),
        crawl_record.metadata_json.as_ref(),
    );

    if input.enable_two_pass_enrichment {
        emit(OrchestratorEvent::Phase {
            phase: "enriching".to_string(),
            request_id: Some(request.id),
            model: Some(base_model.clone()),
            title: extracted.title.clone(),
            content_length: Some(content_for_summary.len()),
            detail: Some("two_pass".to_string()),
        })?;
        summary = enrich_summary_two_pass(
            &worker_config,
            request.id,
            &summary,
            &content_for_summary,
            &chosen_lang,
            &base_model,
        )
        .await
        .unwrap_or(summary);
    }

    emit_draft_delta(emit, request.id, Some(&summary))?;
    emit(OrchestratorEvent::Phase {
        phase: "persisting".to_string(),
        request_id: Some(request.id),
        model: terminal_model_name.clone(),
        title: extracted.title.clone(),
        content_length: Some(content_for_summary.len()),
        detail: None,
    })?;

    let summary_record = upsert_summary(
        &connection,
        &UpsertSummaryInput {
            request_id: request.id,
            lang: chosen_lang.clone(),
            json_payload: summary.clone(),
            insights_json: None,
            is_read: input.persist_is_read.unwrap_or(!input.silent),
        },
    )?;
    update_request_status(&connection, request.id, "ok")?;
    write_summary_cache(
        &dedupe_hash,
        &input.prompt_version,
        terminal_model_name.as_deref().unwrap_or(&base_model),
        &chosen_lang,
        &summary,
    )?;

    let result = ProcessingTerminalResult {
        status: "ok".to_string(),
        request_id: Some(request.id),
        summary_id: Some(summary_record.id),
        summary: Some(summary.clone()),
        title: extracted.title.or_else(|| summary_title(&summary)),
        detected_language: Some(detected_language),
        chosen_lang: Some(chosen_lang),
        needs_ru_translation,
        cached: false,
        model: terminal_model_name.or(Some(base_model)),
        chunk_count,
        error_code: None,
        error_text: None,
        dedupe_hash: Some(dedupe_hash),
        content_text: Some(extracted.content_text),
    };

    emit(OrchestratorEvent::Phase {
        phase: "completed".to_string(),
        request_id: Some(request.id),
        model: result.model.clone(),
        title: result.title.clone(),
        content_length: result.content_text.as_ref().map(String::len),
        detail: None,
    })?;
    emit(OrchestratorEvent::Result {
        payload: result.clone(),
    })?;
    Ok(result)
}

pub async fn execute_forward_flow<F>(
    input: &ForwardExecuteInput,
    emit: &mut F,
) -> Result<ProcessingTerminalResult, ExecutionError>
where
    F: FnMut(OrchestratorEvent) -> Result<(), ExecutionError>,
{
    if input.text.trim().is_empty() {
        return Ok(ProcessingTerminalResult {
            status: "error".to_string(),
            request_id: None,
            summary_id: None,
            summary: None,
            title: None,
            detected_language: None,
            chosen_lang: None,
            needs_ru_translation: false,
            cached: false,
            model: None,
            chunk_count: None,
            error_code: Some("empty_forward_text".to_string()),
            error_text: Some("Forwarded message has no text content".to_string()),
            dedupe_hash: None,
            content_text: None,
        });
    }

    let db_path = resolve_db_path(input.db_path.as_deref());
    let connection = open_connection(db_path)?;
    let plan = build_forward_processing_plan(&ForwardProcessingPlanInput {
        text: input.text.clone(),
        source_chat_title: input.source_chat_title.clone(),
        source_user_first_name: input.source_user_first_name.clone(),
        source_user_last_name: input.source_user_last_name.clone(),
        forward_sender_name: input.forward_sender_name.clone(),
        preferred_language: input.preferred_language.clone(),
        primary_model: input.primary_model.clone(),
    });

    let prompt = if input.normalize_forward_prompt {
        normalize_text(plan.prompt.as_str())
    } else {
        plan.prompt.clone()
    };

    let existing_request = match (input.fwd_from_chat_id, input.fwd_from_msg_id) {
        (Some(chat_id), Some(msg_id)) => get_request_by_forward(&connection, chat_id, msg_id)?,
        _ => None,
    };

    let request = if let Some(existing_request_id) = input.existing_request_id {
        let request = bsr_persistence::get_request_by_id(&connection, existing_request_id)?
            .ok_or_else(|| {
                ExecutionError::InvalidInput("existing request not found".to_string())
            })?;
        if let Some(correlation_id) = input.correlation_id.as_deref() {
            update_request_correlation_id(&connection, request.id, correlation_id)?;
        }
        request
    } else if let Some(request) = existing_request {
        if let Some(correlation_id) = input.correlation_id.as_deref() {
            update_request_correlation_id(&connection, request.id, correlation_id)?;
        }
        request
    } else {
        create_request(
            &connection,
            &CreateRequestInput {
                request_type: "forward".to_string(),
                status: "pending".to_string(),
                correlation_id: input.correlation_id.clone(),
                chat_id: input.chat_id,
                user_id: input.user_id,
                input_url: None,
                normalized_url: None,
                dedupe_hash: None,
                input_message_id: input.input_message_id,
                fwd_from_chat_id: input.fwd_from_chat_id,
                fwd_from_msg_id: input.fwd_from_msg_id,
                lang_detected: Some(plan.detected_language.clone()),
                content_text: Some(prompt.clone()),
                route_version: input.route_version,
            },
        )?
    };

    emit(OrchestratorEvent::Phase {
        phase: "cache_lookup".to_string(),
        request_id: Some(request.id),
        model: None,
        title: if plan.source_title.is_empty() {
            None
        } else {
            Some(plan.source_title.clone())
        },
        content_length: Some(prompt.len()),
        detail: Some("forward_dedupe_lookup".to_string()),
    })?;

    if let Some(cached_summary) = get_summary_by_request(&connection, request.id)? {
        if let Some(summary_payload) = cached_summary.json_payload.clone() {
            update_request_status(&connection, request.id, "ok")?;
            let result = ProcessingTerminalResult {
                status: "cached".to_string(),
                request_id: Some(request.id),
                summary_id: Some(cached_summary.id),
                summary: Some(summary_payload.clone()),
                title: if plan.source_title.is_empty() {
                    summary_title(&summary_payload)
                } else {
                    Some(plan.source_title.clone())
                },
                detected_language: Some(plan.detected_language.clone()),
                chosen_lang: Some(plan.chosen_lang.clone()),
                needs_ru_translation: false,
                cached: true,
                model: None,
                chunk_count: None,
                error_code: None,
                error_text: None,
                dedupe_hash: None,
                content_text: Some(prompt),
            };
            emit(OrchestratorEvent::Phase {
                phase: "completed".to_string(),
                request_id: Some(request.id),
                model: None,
                title: result.title.clone(),
                content_length: result.content_text.as_ref().map(String::len),
                detail: Some("sqlite_cache_hit".to_string()),
            })?;
            emit(OrchestratorEvent::Result {
                payload: result.clone(),
            })?;
            return Ok(result);
        }
    }

    let system_prompt = load_summary_prompt(&plan.chosen_lang)?;
    let user_content = format!(
        "Summarize the following message to the specified JSON schema. Respond in {}.\n\n{}",
        if plan.chosen_lang == LANG_RU {
            "Russian"
        } else {
            "English"
        },
        plan.llm_prompt
    );
    let messages = vec![
        json!({"role": "system", "content": system_prompt}),
        json!({"role": "user", "content": user_content}),
    ];
    let requests = vec![WorkerRequestConfig {
        preset_name: Some("forward_text".to_string()),
        messages,
        response_format: build_response_format(&input.structured_output_mode),
        max_tokens: Some(plan.llm_max_tokens),
        temperature: Some(input.temperature),
        top_p: input.top_p,
        model_override: Some(input.primary_model.clone()),
    }];

    emit(OrchestratorEvent::Phase {
        phase: "summarizing".to_string(),
        request_id: Some(request.id),
        model: Some(input.primary_model.clone()),
        title: if plan.source_title.is_empty() {
            None
        } else {
            Some(plan.source_title.clone())
        },
        content_length: Some(plan.llm_prompt.len()),
        detail: None,
    })?;

    let worker_config = OpenRouterRuntimeConfig::from_env()?;
    let worker_output = execute_forward_text(
        &WorkerExecutionInput {
            request_id: Some(request.id),
            requests,
        },
        &worker_config,
    )
    .await?;

    persist_attempts(&connection, request.id, &worker_output.attempts, emit)?;

    if worker_output.status != "ok" {
        let result = fail_request(
            &connection,
            request.id,
            "LLM_SUMMARY_FAILED",
            worker_output
                .error_text
                .as_deref()
                .unwrap_or("Summary generation failed"),
            json!({
                "stage": "summarizing",
                "component": "openrouter",
                "reason_code": "LLM_SUMMARY_FAILED",
                "request_id": request.id,
            }),
        )?;
        emit(OrchestratorEvent::Phase {
            phase: "failed".to_string(),
            request_id: Some(request.id),
            model: Some(input.primary_model.clone()),
            title: if plan.source_title.is_empty() {
                None
            } else {
                Some(plan.source_title.clone())
            },
            content_length: Some(plan.llm_prompt.len()),
            detail: result.error_text.clone(),
        })?;
        emit(OrchestratorEvent::Result {
            payload: result.clone(),
        })?;
        return Ok(result);
    }

    let terminal_model_name = terminal_model(&worker_output).or(Some(input.primary_model.clone()));
    let mut summary = worker_output.summary.clone().unwrap_or_else(|| json!({}));
    if input.enable_two_pass_enrichment {
        emit(OrchestratorEvent::Phase {
            phase: "enriching".to_string(),
            request_id: Some(request.id),
            model: Some(input.primary_model.clone()),
            title: if plan.source_title.is_empty() {
                None
            } else {
                Some(plan.source_title.clone())
            },
            content_length: Some(plan.llm_prompt.len()),
            detail: Some("two_pass".to_string()),
        })?;
        summary = enrich_summary_two_pass(
            &worker_config,
            request.id,
            &summary,
            &plan.llm_prompt,
            &plan.chosen_lang,
            &input.primary_model,
        )
        .await
        .unwrap_or(summary);
    }
    emit_draft_delta(emit, request.id, Some(&summary))?;

    emit(OrchestratorEvent::Phase {
        phase: "persisting".to_string(),
        request_id: Some(request.id),
        model: terminal_model_name.clone(),
        title: if plan.source_title.is_empty() {
            None
        } else {
            Some(plan.source_title.clone())
        },
        content_length: Some(plan.llm_prompt.len()),
        detail: None,
    })?;

    let summary_record = upsert_summary(
        &connection,
        &UpsertSummaryInput {
            request_id: request.id,
            lang: plan.chosen_lang.clone(),
            json_payload: summary.clone(),
            insights_json: None,
            is_read: input.persist_is_read.unwrap_or(true),
        },
    )?;
    update_request_status(&connection, request.id, "ok")?;

    let result = ProcessingTerminalResult {
        status: "ok".to_string(),
        request_id: Some(request.id),
        summary_id: Some(summary_record.id),
        summary: Some(summary.clone()),
        title: if plan.source_title.is_empty() {
            summary_title(&summary)
        } else {
            Some(plan.source_title.clone())
        },
        detected_language: Some(plan.detected_language.clone()),
        chosen_lang: Some(plan.chosen_lang.clone()),
        needs_ru_translation: false,
        cached: false,
        model: terminal_model_name,
        chunk_count: None,
        error_code: None,
        error_text: None,
        dedupe_hash: None,
        content_text: Some(prompt),
    };

    emit(OrchestratorEvent::Phase {
        phase: "completed".to_string(),
        request_id: Some(request.id),
        model: result.model.clone(),
        title: result.title.clone(),
        content_length: result.content_text.as_ref().map(String::len),
        detail: None,
    })?;
    emit(OrchestratorEvent::Result {
        payload: result.clone(),
    })?;
    Ok(result)
}

impl FirecrawlRuntimeConfig {
    fn from_env() -> Self {
        let base_url = env::var("FIRECRAWL_SELF_HOSTED_URL")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| FIRECRAWL_BASE_URL.to_string());
        let api_key = env::var("FIRECRAWL_SELF_HOSTED_API_KEY")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .or_else(|| {
                env::var("FIRECRAWL_API_KEY")
                    .ok()
                    .filter(|value| !value.trim().is_empty())
            });
        let timeout_sec = env::var("FIRECRAWL_TIMEOUT_SEC")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(90);
        let wait_for_ms = env::var("FIRECRAWL_WAIT_FOR_MS")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(3000);
        let max_age_seconds = env::var("FIRECRAWL_MAX_AGE_SECONDS")
            .ok()
            .and_then(|value| value.parse::<i64>().ok())
            .unwrap_or(172_800);
        Self {
            api_key,
            base_url: base_url.trim_end_matches('/').to_string(),
            timeout: Duration::from_secs(timeout_sec.max(10)),
            wait_for_ms,
            max_age_seconds,
            include_markdown: parse_bool_env("FIRECRAWL_INCLUDE_MARKDOWN", true),
            include_html: parse_bool_env("FIRECRAWL_INCLUDE_HTML", true),
            include_images: parse_bool_env("FIRECRAWL_INCLUDE_IMAGES", false),
            block_ads: parse_bool_env("FIRECRAWL_BLOCK_ADS", true),
            remove_base64_images: parse_bool_env("FIRECRAWL_REMOVE_BASE64_IMAGES", true),
            skip_tls_verification: parse_bool_env("FIRECRAWL_SKIP_TLS_VERIFICATION", true),
        }
    }
}

async fn scrape_url(
    config: &FirecrawlRuntimeConfig,
    url: &str,
    correlation_id: Option<&str>,
) -> Result<FirecrawlResult, ExecutionError> {
    let mut headers = HeaderMap::new();
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    if let Some(api_key) = config.api_key.as_deref() {
        let value = HeaderValue::from_str(&format!("Bearer {api_key}"))
            .map_err(|_| ExecutionError::InvalidFirecrawlHeader)?;
        headers.insert(AUTHORIZATION, value);
    }
    let client = Client::builder().timeout(config.timeout).build()?;
    let formats = build_firecrawl_formats(config);
    let options = json!({
        "mobile": true,
        "maxAge": config.max_age_seconds,
        "removeBase64Images": config.remove_base64_images,
        "blockAds": config.block_ads,
        "skipTlsVerification": config.skip_tls_verification,
        "waitFor": config.wait_for_ms,
        "formats": formats,
    });
    let body = json!({
        "url": url,
        "mobile": true,
        "maxAge": config.max_age_seconds,
        "removeBase64Images": config.remove_base64_images,
        "blockAds": config.block_ads,
        "skipTlsVerification": config.skip_tls_verification,
        "waitFor": config.wait_for_ms,
        "formats": formats,
    });
    let started = std::time::Instant::now();
    let response = client
        .post(format!("{}{}", config.base_url, FIRECRAWL_SCRAPE_ENDPOINT))
        .headers(headers)
        .json(&body)
        .send()
        .await?;
    let latency_ms = started.elapsed().as_millis() as i64;
    let http_status = i64::from(response.status().as_u16());
    let json_body: Value = response.json().await.unwrap_or_else(|_| json!({}));

    let success = json_body
        .get("success")
        .and_then(Value::as_bool)
        .unwrap_or(http_status < 400);
    let data = json_body.get("data").and_then(Value::as_object);
    let metadata = data
        .and_then(|object| object.get("metadata"))
        .cloned()
        .or_else(|| json_body.get("metadata").cloned());

    Ok(FirecrawlResult {
        status: if success { "success" } else { "error" }.to_string(),
        http_status: Some(http_status),
        content_markdown: data
            .and_then(|object| object.get("markdown"))
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        content_html: data
            .and_then(|object| object.get("html"))
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        structured_json: data.and_then(|object| object.get("json")).cloned(),
        metadata_json: metadata,
        links_json: data.and_then(|object| object.get("links")).cloned(),
        response_success: Some(success),
        response_error_code: json_body
            .get("error")
            .and_then(Value::as_object)
            .and_then(|object| object.get("code"))
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        response_error_message: json_body
            .get("error")
            .and_then(Value::as_object)
            .and_then(|object| object.get("message"))
            .and_then(Value::as_str)
            .map(ToOwned::to_owned),
        response_details: json_body
            .get("error")
            .and_then(Value::as_object)
            .and_then(|object| object.get("details"))
            .cloned(),
        latency_ms: Some(latency_ms),
        error_text: if success {
            None
        } else {
            json_body
                .get("error")
                .and_then(Value::as_object)
                .and_then(|object| object.get("message"))
                .and_then(Value::as_str)
                .map(ToOwned::to_owned)
                .or_else(|| Some(format!("HTTP {http_status}")))
        },
        source_url: Some(url.to_string()),
        endpoint: Some(FIRECRAWL_SCRAPE_ENDPOINT.to_string()),
        options_json: Some(options),
        correlation_id: correlation_id.map(ToOwned::to_owned),
    })
}

fn build_firecrawl_formats(config: &FirecrawlRuntimeConfig) -> Vec<Value> {
    let mut formats = Vec::new();
    if config.include_markdown {
        formats.push(Value::String("markdown".to_string()));
    }
    if config.include_html {
        formats.push(Value::String("html".to_string()));
    }
    if config.include_images {
        formats.push(Value::String("images".to_string()));
    }
    if formats.is_empty() {
        formats.push(Value::String("markdown".to_string()));
    }
    formats
}

struct UrlWorkerSettings {
    system_prompt: String,
    chosen_lang: String,
    structured_output_mode: String,
    temperature: f64,
    top_p: Option<f64>,
    json_temperature: Option<f64>,
    json_top_p: Option<f64>,
    primary_model: String,
}

async fn execute_chunked_flow(
    worker_config: &OpenRouterRuntimeConfig,
    plan: &crate::UrlProcessingPlan,
    settings: &UrlWorkerSettings,
    request_id: i64,
) -> Result<(WorkerExecutionOutput, Option<usize>), ExecutionError> {
    let chunk_plan = plan
        .chunk_plan
        .as_ref()
        .ok_or_else(|| ExecutionError::InvalidInput("chunk plan missing".to_string()))?;
    let chunk_requests = chunk_plan
        .chunks
        .iter()
        .enumerate()
        .map(|(index, chunk)| WorkerRequestConfig {
            preset_name: Some(format!("chunk_{}", index + 1)),
            messages: vec![
                json!({"role": "system", "content": settings.system_prompt}),
                json!({
                    "role": "user",
                    "content": format!(
                        "Analyze this part {}/{} and output ONLY a valid JSON object matching the schema. Respond in {}.\n\nCONTENT START\n{}\nCONTENT END",
                        index + 1,
                        chunk_plan.chunks.len(),
                        if settings.chosen_lang == LANG_RU { "Russian" } else { "English" },
                        chunk
                    )
                }),
            ],
            response_format: build_response_format(&settings.structured_output_mode),
            max_tokens: Some(select_chunk_tokens(chunk)),
            temperature: Some(settings.temperature),
            top_p: settings.top_p,
            model_override: Some(settings.primary_model.clone()),
        })
        .collect::<Vec<_>>();

    let output = execute_chunked_url(
        &ChunkedUrlExecutionInput {
            request_id: Some(request_id),
            chunk_requests,
            synthesis: WorkerChunkedSynthesisConfig {
                preset_name: Some("chunk_synthesis".to_string()),
                system_prompt: settings.system_prompt.clone(),
                chosen_lang: settings.chosen_lang.clone(),
                response_format: build_response_format(&settings.structured_output_mode),
                max_tokens: Some(4096),
                temperature: settings.json_temperature.or(Some(settings.temperature)),
                top_p: settings.json_top_p.or(settings.top_p),
                model_override: Some(settings.primary_model.clone()),
            },
            max_concurrent_calls: 4,
        },
        worker_config,
    )
    .await?;

    Ok((
        WorkerExecutionOutput {
            status: output.status,
            summary: output.summary,
            attempts: output.attempts,
            terminal_attempt_index: output.terminal_attempt_index,
            error_text: output.error_text,
        },
        Some(chunk_plan.chunks.len()),
    ))
}

async fn enrich_summary_two_pass(
    worker_config: &OpenRouterRuntimeConfig,
    request_id: i64,
    summary: &Value,
    content_text: &str,
    chosen_lang: &str,
    model: &str,
) -> Result<Value, ExecutionError> {
    let enrichment_prompt = load_enrichment_prompt(chosen_lang)?;
    let trimmed_content = content_text.chars().take(30_000).collect::<String>();
    let core_summary = json!({
        "summary_250": summary.get("summary_250").cloned().unwrap_or(Value::Null),
        "summary_1000": summary.get("summary_1000").cloned().unwrap_or(Value::Null),
        "tldr": summary.get("tldr").cloned().unwrap_or(Value::Null),
        "key_ideas": summary.get("key_ideas").cloned().unwrap_or_else(|| json!([])),
        "topic_tags": summary.get("topic_tags").cloned().unwrap_or_else(|| json!([])),
        "entities": summary.get("entities").cloned().unwrap_or_else(|| json!({})),
        "source_type": summary.get("source_type").cloned().unwrap_or(Value::Null),
    });
    let user_content = format!(
        "Respond in {}.\n\nCORE SUMMARY (already generated, do not modify):\n{}\n\nORIGINAL CONTENT START\n{}\nORIGINAL CONTENT END",
        if chosen_lang == LANG_RU { "Russian" } else { "English" },
        serde_json::to_string_pretty(&core_summary)?,
        trimmed_content,
    );
    let output = execute_url_single_pass(
        &WorkerExecutionInput {
            request_id: Some(request_id),
            requests: vec![WorkerRequestConfig {
                preset_name: Some("two_pass_enrichment".to_string()),
                messages: vec![
                    json!({"role": "system", "content": enrichment_prompt}),
                    json!({"role": "user", "content": user_content}),
                ],
                response_format: json!({"type": "json_object"}),
                max_tokens: Some(4096),
                temperature: Some(0.2),
                top_p: Some(0.9),
                model_override: Some(model.to_string()),
            }],
        },
        worker_config,
    )
    .await?;
    if output.status != "ok" {
        return Ok(summary.clone());
    }
    let enrichment = output.summary.unwrap_or_else(|| json!({}));
    let mut merged = summary.as_object().cloned().unwrap_or_default();
    for key in [
        "answered_questions",
        "seo_keywords",
        "extractive_quotes",
        "highlights",
        "categories",
        "key_points_to_remember",
        "questions_answered",
        "topic_taxonomy",
    ] {
        if let Some(value) = enrichment.get(key) {
            if !value.is_null() {
                merged.insert(key.to_string(), value.clone());
            }
        }
    }
    Ok(Value::Object(merged))
}

fn persist_attempts<F>(
    connection: &Connection,
    request_id: i64,
    attempts: &[WorkerAttemptOutput],
    emit: &mut F,
) -> Result<(), ExecutionError>
where
    F: FnMut(OrchestratorEvent) -> Result<(), ExecutionError>,
{
    for (index, attempt) in attempts.iter().enumerate() {
        insert_llm_call(
            connection,
            &InsertLlmCallInput {
                request_id,
                provider: Some("openrouter".to_string()),
                model: attempt.llm_result.model.clone(),
                endpoint: Some(attempt.llm_result.endpoint.clone()),
                request_headers_json: attempt.llm_result.request_headers.clone(),
                request_messages_json: attempt
                    .llm_result
                    .request_messages
                    .clone()
                    .map(Value::Array),
                response_text: attempt.llm_result.response_text.clone(),
                response_json: attempt.llm_result.response_json.clone(),
                openrouter_response_text: attempt.llm_result.openrouter_response_text.clone(),
                openrouter_response_json: attempt.llm_result.openrouter_response_json.clone(),
                tokens_prompt: attempt.llm_result.tokens_prompt,
                tokens_completion: attempt.llm_result.tokens_completion,
                cost_usd: attempt.llm_result.cost_usd,
                latency_ms: attempt.llm_result.latency_ms,
                status: Some(attempt.llm_result.status.clone()),
                error_text: attempt.llm_result.error_text.clone(),
                structured_output_used: Some(attempt.llm_result.structured_output_used),
                structured_output_mode: attempt.llm_result.structured_output_mode.clone(),
                error_context_json: attempt.llm_result.error_context.clone(),
            },
        )?;
        emit(OrchestratorEvent::Attempt {
            request_id: Some(request_id),
            attempt_index: index,
            preset_name: attempt.preset_name.clone(),
            model_override: attempt.model_override.clone(),
            llm_result: attempt.llm_result.clone(),
        })?;
    }
    Ok(())
}

fn emit_draft_delta<F>(
    emit: &mut F,
    request_id: i64,
    summary: Option<&Value>,
) -> Result<(), ExecutionError>
where
    F: FnMut(OrchestratorEvent) -> Result<(), ExecutionError>,
{
    let Some(summary) = summary else {
        return Ok(());
    };
    if let Some(text) = summary.get("summary_250").and_then(Value::as_str) {
        if !text.trim().is_empty() {
            emit(OrchestratorEvent::DraftDelta {
                request_id: Some(request_id),
                field: Some("summary_250".to_string()),
                delta: text.to_string(),
            })?;
        }
    }
    if let Some(text) = summary.get("tldr").and_then(Value::as_str) {
        if !text.trim().is_empty() {
            emit(OrchestratorEvent::DraftDelta {
                request_id: Some(request_id),
                field: Some("tldr".to_string()),
                delta: text.to_string(),
            })?;
        }
    }
    Ok(())
}

fn fail_request(
    connection: &Connection,
    request_id: i64,
    error_code: &str,
    error_text: &str,
    error_context: Value,
) -> Result<ProcessingTerminalResult, ExecutionError> {
    update_request_error(
        connection,
        request_id,
        &RequestErrorUpdate {
            status: "error".to_string(),
            error_type: Some(error_code.to_string()),
            error_message: Some(error_text.to_string()),
            processing_time_ms: None,
            error_context_json: Some(error_context),
        },
    )?;
    Ok(ProcessingTerminalResult {
        status: "error".to_string(),
        request_id: Some(request_id),
        summary_id: None,
        summary: None,
        title: None,
        detected_language: None,
        chosen_lang: None,
        needs_ru_translation: false,
        cached: false,
        model: None,
        chunk_count: None,
        error_code: Some(error_code.to_string()),
        error_text: Some(error_text.to_string()),
        dedupe_hash: None,
        content_text: None,
    })
}

fn terminal_model(output: &WorkerExecutionOutput) -> Option<String> {
    output
        .terminal_attempt_index
        .and_then(|index| output.attempts.get(index))
        .and_then(|attempt| attempt.llm_result.model.clone())
}

fn build_response_format(mode: &str) -> Value {
    if mode == "json_schema" {
        json!({
            "type": "json_schema",
            "json_schema": {
                "name": "summary_schema",
                "strict": true,
                "schema": build_summary_schema(),
            }
        })
    } else {
        json!({"type": "json_object"})
    }
}

fn build_summary_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": true,
        "required": ["summary_250", "summary_1000", "tldr"],
        "properties": {
            "summary_250": {"type": "string"},
            "summary_1000": {"type": "string"},
            "tldr": {"type": "string"},
            "key_ideas": {"type": "array", "items": {"type": "string"}},
            "topic_tags": {"type": "array", "items": {"type": "string"}},
            "entities": {"type": "object"},
            "source_type": {"type": "string"},
            "temporal_freshness": {"type": "string"},
            "estimated_reading_time_min": {"type": "integer"},
            "key_stats": {"type": "array"},
            "readability": {"type": "object"},
            "confidence": {"type": "number"},
            "hallucination_risk": {"type": "string"},
            "metadata": {"type": "object"},
            "insights": {"type": "object"},
            "quality": {"type": "object"}
        }
    })
}

fn build_summary_requests(
    messages: &[Value],
    base_model: &str,
    structured_output_mode: &str,
    fallback_models: &[String],
    flash_model: Option<&str>,
    flash_fallback_models: &[String],
    temperature: f64,
    top_p: Option<f64>,
    json_temperature: Option<f64>,
    json_top_p: Option<f64>,
    content_for_summary: &str,
    user_content: &str,
) -> Vec<WorkerRequestConfig> {
    let base_top_p = top_p.unwrap_or(0.9);
    let effective_json_temperature =
        json_temperature.unwrap_or((temperature - 0.05).clamp(0.0, 0.5));
    let effective_json_top_p = json_top_p.unwrap_or(base_top_p.clamp(0.0, 0.95));
    let schema_format = build_response_format(structured_output_mode);
    let json_object_format = json!({"type": "json_object"});
    let max_tokens_schema = select_max_tokens(content_for_summary);
    let max_tokens_json_object = select_max_tokens(user_content);

    let mut requests = vec![
        WorkerRequestConfig {
            preset_name: Some("schema_strict".to_string()),
            messages: messages.to_vec(),
            response_format: schema_format,
            max_tokens: Some(max_tokens_schema),
            temperature: Some(temperature),
            top_p: Some(base_top_p),
            model_override: Some(base_model.to_string()),
        },
        WorkerRequestConfig {
            preset_name: Some("json_object_guardrail".to_string()),
            messages: messages.to_vec(),
            response_format: json_object_format.clone(),
            max_tokens: Some(max_tokens_json_object),
            temperature: Some(effective_json_temperature),
            top_p: Some(effective_json_top_p),
            model_override: Some(base_model.to_string()),
        },
    ];

    let mut added_flash_models = Vec::new();
    if let Some(model) = flash_model {
        if model != base_model {
            requests.push(WorkerRequestConfig {
                preset_name: Some("json_object_flash".to_string()),
                messages: messages.to_vec(),
                response_format: json_object_format.clone(),
                max_tokens: Some(max_tokens_json_object),
                temperature: Some(effective_json_temperature),
                top_p: Some(effective_json_top_p),
                model_override: Some(model.to_string()),
            });
            added_flash_models.push(model.to_string());
        }
    }
    for model in flash_fallback_models {
        if model != base_model && !added_flash_models.contains(model) {
            requests.push(WorkerRequestConfig {
                preset_name: Some("json_object_flash".to_string()),
                messages: messages.to_vec(),
                response_format: json_object_format.clone(),
                max_tokens: Some(max_tokens_json_object),
                temperature: Some(effective_json_temperature),
                top_p: Some(effective_json_top_p),
                model_override: Some(model.clone()),
            });
            added_flash_models.push(model.clone());
        }
    }
    if let Some(model) = fallback_models
        .iter()
        .find(|model| model.as_str() != base_model && !added_flash_models.contains(*model))
    {
        requests.push(WorkerRequestConfig {
            preset_name: Some("json_object_fallback".to_string()),
            messages: messages.to_vec(),
            response_format: json_object_format,
            max_tokens: Some(max_tokens_json_object),
            temperature: Some(effective_json_temperature),
            top_p: Some(effective_json_top_p),
            model_override: Some(model.clone()),
        });
    }
    requests
}

fn build_summary_messages(
    system_prompt: &str,
    user_content: &str,
    images: &[String],
) -> Vec<Value> {
    if images.is_empty() {
        return vec![
            json!({"role": "system", "content": system_prompt}),
            json!({"role": "user", "content": user_content}),
        ];
    }
    let mut content_parts = vec![json!({"type": "text", "text": user_content})];
    for image in images {
        content_parts.push(json!({"type": "image_url", "image_url": {"url": image}}));
    }
    vec![
        json!({"role": "system", "content": system_prompt}),
        json!({"role": "user", "content": content_parts}),
    ]
}

fn build_summary_user_content(
    content_for_summary: &str,
    chosen_lang: &str,
    search_context: &str,
) -> String {
    let response_language = if chosen_lang == LANG_RU {
        "Russian"
    } else {
        "English"
    };
    let base = format!(
        "Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. Respond in {response_language}. Do NOT include any text outside the JSON.\n\nCONTENT START\n{content_for_summary}\nCONTENT END"
    );
    if search_context.trim().is_empty() {
        base
    } else {
        format!("{base}\n\n{search_context}")
    }
}

fn select_max_tokens(content_text: &str) -> i64 {
    let approx_input_tokens = (content_text.chars().count() / 4) as i64;
    (approx_input_tokens / 2 + 2048).clamp(4096, 12_288)
}

fn select_chunk_tokens(chunk: &str) -> i64 {
    ((chunk.chars().count() / 4) as i64 + 1024).clamp(1024, 4096)
}

fn prepare_summary_content(
    content_text: &str,
    max_chars: usize,
    long_context_model: Option<&str>,
    vision_model: Option<&str>,
    has_images: bool,
    primary_model: &str,
) -> (String, String) {
    let mut content = content_text.to_string();
    let mut model = if has_images {
        vision_model.unwrap_or(primary_model).to_string()
    } else {
        primary_model.to_string()
    };
    if content.chars().count() > max_chars {
        if let Some(long_context_model) = long_context_model {
            if !long_context_model.trim().is_empty() {
                model = long_context_model.to_string();
            }
        } else {
            content = content.chars().take(max_chars).collect::<String>();
        }
    }
    (clean_content_for_llm(&content), model)
}

struct ExtractedUrlContent {
    content_text: String,
    title: Option<String>,
    images: Vec<String>,
}

fn extract_content_text(result: &FirecrawlResult) -> ExtractedUrlContent {
    let title = extract_title_from_metadata(result.metadata_json.as_ref());
    let images = extract_images(result);
    if let Some(markdown) = result.content_markdown.as_deref() {
        let cleaned = clean_markdown_article_text(markdown);
        if !cleaned.trim().is_empty() {
            return ExtractedUrlContent {
                content_text: cleaned,
                title,
                images,
            };
        }
    }
    if let Some(html) = result.content_html.as_deref() {
        return ExtractedUrlContent {
            content_text: html_to_text(html),
            title,
            images,
        };
    }
    ExtractedUrlContent {
        content_text: String::new(),
        title,
        images,
    }
}

fn extract_title_from_metadata(metadata: Option<&Value>) -> Option<String> {
    let object = metadata.and_then(Value::as_object)?;
    for key in [
        "title",
        "og:title",
        "og_title",
        "meta_title",
        "twitter:title",
        "headline",
    ] {
        if let Some(value) = object.get(key).and_then(Value::as_str) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
    }
    None
}

fn extract_images(result: &FirecrawlResult) -> Vec<String> {
    let mut images = Vec::new();
    let mut seen = std::collections::HashSet::new();
    if let Some(metadata) = result.metadata_json.as_ref().and_then(Value::as_object) {
        if let Some(screenshots) = metadata.get("screenshots") {
            match screenshots {
                Value::Array(items) => {
                    for item in items {
                        if let Some(url) = item.as_str() {
                            if url.starts_with("http") && seen.insert(url.to_string()) {
                                images.push(url.to_string());
                            }
                        }
                    }
                }
                Value::String(url) => {
                    if url.starts_with("http") && seen.insert(url.clone()) {
                        images.push(url.clone());
                    }
                }
                _ => {}
            }
        }
    }

    if let Some(markdown) = result.content_markdown.as_deref() {
        let re = Regex::new(r"!\[[^\]]*\]\((https?://[^\s\)]+)\)").expect("markdown image regex");
        for captures in re.captures_iter(markdown) {
            let url = captures
                .get(1)
                .map(|value| value.as_str())
                .unwrap_or_default();
            let lowered = url.to_ascii_lowercase();
            if lowered.contains("icon")
                || lowered.contains("logo")
                || lowered.contains("tracker")
                || lowered.contains("pixel")
                || lowered.ends_with(".svg")
                || lowered.ends_with(".ico")
            {
                continue;
            }
            if !url.is_empty() && seen.insert(url.to_string()) {
                images.push(url.to_string());
            }
        }
    }

    images.truncate(5);
    images
}

fn detect_low_value_content(result: &FirecrawlResult) -> Option<Value> {
    let mut candidates = Vec::new();
    if let Some(markdown) = result.content_markdown.as_deref() {
        candidates.push(clean_markdown_article_text(markdown));
    }
    if let Some(html) = result.content_html.as_deref() {
        candidates.push(html_to_text(html));
    }
    let primary_text = candidates
        .into_iter()
        .find(|candidate| !candidate.trim().is_empty())
        .unwrap_or_default();
    let normalized = Regex::new(r"\s+")
        .expect("whitespace regex")
        .replace_all(primary_text.trim(), " ")
        .to_string();
    let word_re = Regex::new(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ']+").expect("word regex");
    let words = word_re
        .find_iter(&normalized)
        .map(|match_| match_.as_str().to_ascii_lowercase())
        .collect::<Vec<_>>();
    let word_count = words.len();
    let unique_word_count = words.iter().collect::<std::collections::HashSet<_>>().len();
    let mut top_word = None;
    let mut top_ratio = 0.0_f64;
    if !words.is_empty() {
        let mut counts = std::collections::HashMap::<String, usize>::new();
        for word in &words {
            *counts.entry(word.clone()).or_default() += 1;
        }
        if let Some((word, count)) = counts.iter().max_by_key(|(_, count)| *count) {
            top_word = Some(word.clone());
            top_ratio = *count as f64 / word_count as f64;
        }
    }

    let overlay_terms = [
        "accept",
        "close",
        "cookie",
        "cookies",
        "consent",
        "login",
        "signin",
        "signup",
        "subscribe",
    ];
    let overlay_ratio = if word_count == 0 {
        0.0
    } else {
        words
            .iter()
            .filter(|word| overlay_terms.contains(&word.as_str()))
            .count() as f64
            / word_count as f64
    };

    let reason = if normalized.is_empty() || word_count == 0 {
        Some("empty_after_cleaning")
    } else if overlay_ratio >= 0.7 && normalized.len() < 600 {
        Some("overlay_content_detected")
    } else if normalized.len() < 48 && word_count <= 2 {
        Some("content_too_short")
    } else if normalized.len() < 120
        && (unique_word_count <= 3 || (word_count >= 4 && top_ratio >= 0.8))
    {
        Some("content_low_variation")
    } else if word_count >= 6 && top_ratio >= 0.92 {
        Some("content_high_repetition")
    } else {
        None
    };

    reason.map(|reason| {
        json!({
            "reason": reason,
            "preview": normalized.chars().take(200).collect::<String>(),
            "metrics": {
                "char_length": normalized.len(),
                "word_count": word_count,
                "unique_word_count": unique_word_count,
                "top_word": top_word,
                "top_ratio": top_ratio,
                "overlay_ratio": overlay_ratio,
            }
        })
    })
}

fn ensure_summary_metadata(
    summary: Value,
    extracted_title: Option<&str>,
    canonical_url: Option<&str>,
    crawl_metadata: Option<&Value>,
) -> Value {
    let mut shaped = validate_and_shape_summary(&summary).unwrap_or(summary);
    let Some(object) = shaped.as_object_mut() else {
        return shaped;
    };

    let metadata_value = object
        .entry("metadata".to_string())
        .or_insert_with(|| json!({}));
    if !metadata_value.is_object() {
        *metadata_value = json!({});
    }
    let metadata = metadata_value
        .as_object_mut()
        .expect("metadata should be object");

    if metadata.get("title").map(is_blank_json).unwrap_or(true) {
        if let Some(title) = extracted_title.filter(|value| !value.trim().is_empty()) {
            metadata.insert("title".to_string(), Value::String(title.to_string()));
        }
    }
    if metadata
        .get("canonical_url")
        .map(is_blank_json)
        .unwrap_or(true)
    {
        if let Some(url) = canonical_url.filter(|value| !value.trim().is_empty()) {
            metadata.insert("canonical_url".to_string(), Value::String(url.to_string()));
        }
    }
    if metadata.get("domain").map(is_blank_json).unwrap_or(true) {
        if let Some(url) = canonical_url {
            if let Ok(parsed) = Url::parse(url) {
                if let Some(domain) = parsed.domain() {
                    metadata.insert("domain".to_string(), Value::String(domain.to_string()));
                }
            }
        }
    }
    if let Some(crawl_metadata) = crawl_metadata.and_then(Value::as_object) {
        for (target_key, aliases) in [
            ("author", ["author", "article:author", "byline"].as_slice()),
            (
                "published_at",
                ["article:published_time", "article:published", "published"].as_slice(),
            ),
            (
                "last_updated",
                ["article:modified_time", "updated", "lastmod"].as_slice(),
            ),
        ] {
            if metadata.get(target_key).map(is_blank_json).unwrap_or(true) {
                for alias in aliases {
                    if let Some(value) = crawl_metadata.get(*alias).and_then(Value::as_str) {
                        if !value.trim().is_empty() {
                            metadata
                                .insert(target_key.to_string(), Value::String(value.to_string()));
                            break;
                        }
                    }
                }
            }
        }
    }
    shaped
}

fn is_blank_json(value: &Value) -> bool {
    match value {
        Value::Null => true,
        Value::String(text) => text.trim().is_empty(),
        _ => false,
    }
}

fn summary_title(summary: &Value) -> Option<String> {
    summary
        .get("metadata")
        .and_then(Value::as_object)
        .and_then(|metadata| metadata.get("title"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .or_else(|| {
            summary
                .get("summary_250")
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
                .map(|value| value.chars().take(100).collect())
        })
}

fn resolve_db_path(override_path: Option<&str>) -> String {
    override_path
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .or_else(|| env::var("DB_PATH").ok())
        .unwrap_or_else(|| DEFAULT_DB_PATH.to_string())
}

fn parse_bool_env(key: &str, default: bool) -> bool {
    match env::var(key) {
        Ok(value) => match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => true,
            "0" | "false" | "no" | "off" => false,
            _ => default,
        },
        Err(_) => default,
    }
}

fn normalize_url(input: &str) -> Result<String, ExecutionError> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return Err(ExecutionError::InvalidInput(
            "URL cannot be empty".to_string(),
        ));
    }
    let mut url = if trimmed.contains("://") {
        Url::parse(trimmed)
    } else {
        Url::parse(&format!("https://{trimmed}"))
    }
    .map_err(|error| ExecutionError::InvalidInput(format!("URL normalization failed: {error}")))?;
    url.set_fragment(None);
    let tracking_params = [
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "gclid",
        "fbclid",
    ];
    let mut pairs = url
        .query_pairs()
        .filter(|(key, _)| !tracking_params.contains(&key.as_ref()))
        .map(|(key, value)| (key.to_string(), value.to_string()))
        .collect::<Vec<_>>();
    pairs.sort();
    if pairs.is_empty() {
        url.set_query(None);
    } else {
        let query = pairs
            .iter()
            .map(|(key, value)| format!("{key}={value}"))
            .collect::<Vec<_>>()
            .join("&");
        url.set_query(Some(&query));
    }
    if url.path().is_empty() {
        url.set_path("/");
    }
    Ok(url.to_string())
}

fn url_hash_sha256(normalized_url: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(normalized_url.as_bytes());
    format!("{:x}", hasher.finalize())
}

fn detect_language(text: &str) -> String {
    if text
        .chars()
        .any(|character| ('\u{0400}'..='\u{04FF}').contains(&character))
    {
        LANG_RU.to_string()
    } else {
        LANG_EN.to_string()
    }
}

fn normalize_text(text: &str) -> String {
    let url_re = Regex::new(r"https?://\S+").expect("url regex");
    let email_re = Regex::new(r"\S+@\S+").expect("email regex");
    let phone_re = Regex::new(r"\+?\d[\d\s\-\(\)]{7,}\d").expect("phone regex");
    let control_re = Regex::new(r"[\u0000-\u001F\u007F]").expect("control regex");
    let whitespace_re = Regex::new(r"[ \t]{2,}").expect("whitespace regex");
    let newlines_re = Regex::new(r"\n{3,}").expect("newlines regex");

    let mut output = text.replace('—', "-").replace('–', "-");
    output = url_re.replace_all(&output, " ").to_string();
    output = email_re.replace_all(&output, " ").to_string();
    output = phone_re.replace_all(&output, " ").to_string();
    output = control_re.replace_all(&output, " ").to_string();
    output = whitespace_re.replace_all(&output, " ").to_string();
    output = newlines_re.replace_all(&output, "\n\n").to_string();
    output.trim().to_string()
}

fn clean_content_for_llm(text: &str) -> String {
    let blank_lines_re = Regex::new(r"\n{3,}").expect("blank line regex");
    let link_re = Regex::new(r"\[([^\]]+)\]\([^)]+\)").expect("markdown link regex");
    let comments_re = Regex::new(
        r"(?im)^(?:#{1,4}\s+)?(?:\d+\s+)?(?:comments?|responses?|replies?|discussion)\s*$",
    )
    .expect("comments regex");
    let mut output = text.to_string();
    output = blank_lines_re.replace_all(&output, "\n\n").to_string();
    output = link_re.replace_all(&output, "$1").to_string();
    if let Some(match_) = comments_re.find(&output) {
        output.truncate(match_.start());
    }
    output.trim().to_string()
}

fn clean_markdown_article_text(markdown: &str) -> String {
    let fenced_code_re = Regex::new(r"```[\s\S]*?```").expect("fenced code regex");
    let inline_code_re = Regex::new(r"`[^`]*`").expect("inline code regex");
    let image_re = Regex::new(r"!\[[^\]]*\]\([^\)]+\)").expect("image regex");
    let link_re = Regex::new(r"\[([^\]]+)\]\([^\)]+\)").expect("link regex");
    let ref_re = Regex::new(r"(?m)^\s*\[[^\]]+\]:\s*\S+\s*$").expect("ref regex");
    let spaces_re = Regex::new(r"[ \t]{2,}").expect("spaces regex");
    let newlines_re = Regex::new(r"\n{3,}").expect("newlines regex");

    let mut text = markdown.to_string();
    text = fenced_code_re.replace_all(&text, "").to_string();
    text = inline_code_re.replace_all(&text, "").to_string();
    text = image_re.replace_all(&text, "").to_string();
    text = link_re.replace_all(&text, "$1").to_string();
    text = ref_re.replace_all(&text, "").to_string();

    let drop_prefixes = [
        "share",
        "watch later",
        "copy link",
        "include playlist",
        "tap to unmute",
        "you're signed out",
        "videos you watch",
        "search",
        "info",
        "shopping",
        "cancel",
        "confirm",
        "subscribe",
        "sign in",
        "login",
        "comments",
        "комментарии",
        "поделиться",
    ];
    let drop_exact = ["—", "-", "•", "* * *", "— — —"];
    let url_re = Regex::new(r"^https?://\S+$").expect("plain url regex");

    let mut filtered = Vec::new();
    for line in text.lines() {
        let raw = line.trim();
        if raw.is_empty() {
            filtered.push(String::new());
            continue;
        }
        let lowered = raw.to_ascii_lowercase();
        if drop_prefixes
            .iter()
            .any(|prefix| lowered.starts_with(prefix))
        {
            continue;
        }
        if drop_exact.contains(&raw) || url_re.is_match(raw) {
            continue;
        }
        filtered.push(raw.to_string());
    }

    let mut collapsed = Vec::new();
    let mut prev_blank = false;
    for line in filtered {
        if line.is_empty() {
            if !prev_blank {
                collapsed.push(line);
            }
            prev_blank = true;
        } else {
            collapsed.push(line);
            prev_blank = false;
        }
    }

    let cleaned = spaces_re
        .replace_all(&collapsed.join("\n"), " ")
        .to_string();
    newlines_re.replace_all(cleaned.trim(), "\n\n").to_string()
}

fn html_to_text(html: &str) -> String {
    let script_re = Regex::new(r"(?is)<script[\s\S]*?</script>").expect("script regex");
    let style_re = Regex::new(r"(?is)<style[\s\S]*?</style>").expect("style regex");
    let br_re = Regex::new(r"(?i)<br\s*/?>").expect("br regex");
    let p_re = Regex::new(r"(?i)</p>").expect("p regex");
    let tag_re = Regex::new(r"(?is)<[^>]+>").expect("tag regex");
    let whitespace_re = Regex::new(r"\n{3,}").expect("whitespace regex");
    let mut text = script_re.replace_all(html, "").to_string();
    text = style_re.replace_all(&text, "").to_string();
    text = br_re.replace_all(&text, "\n").to_string();
    text = p_re.replace_all(&text, "\n\n").to_string();
    text = tag_re.replace_all(&text, " ").to_string();
    whitespace_re.replace_all(text.trim(), "\n\n").to_string()
}

fn load_summary_prompt(lang: &str) -> Result<String, ExecutionError> {
    let prompt_root = find_prompt_root()?;
    Ok(
        fs::read_to_string(prompt_root.join(format!("summary_system_{lang}.txt")))?
            .trim()
            .to_string(),
    )
}

fn load_enrichment_prompt(lang: &str) -> Result<String, ExecutionError> {
    let prompt_root = find_prompt_root()?;
    Ok(
        fs::read_to_string(prompt_root.join(format!("enrichment_system_{lang}.txt")))?
            .trim()
            .to_string(),
    )
}

fn find_prompt_root() -> Result<PathBuf, ExecutionError> {
    let current_dir = env::current_dir()?;
    for ancestor in current_dir.ancestors() {
        let candidate = ancestor.join("app").join("prompts");
        if candidate.is_dir() {
            return Ok(candidate);
        }
        let nested = ancestor
            .join("bite-size-reader")
            .join("app")
            .join("prompts");
        if nested.is_dir() {
            return Ok(nested);
        }
    }
    Err(ExecutionError::PromptRootNotFound(
        current_dir.display().to_string(),
    ))
}

fn read_summary_cache(
    url_hash: &str,
    prompt_version: &str,
    chosen_lang: &str,
    model_name: &str,
) -> Result<Option<Value>, ExecutionError> {
    let prefix = env::var("REDIS_PREFIX").unwrap_or_else(|_| "bsr".to_string());
    let enabled =
        parse_bool_env("REDIS_ENABLED", true) && parse_bool_env("REDIS_CACHE_ENABLED", true);
    if !enabled {
        return Ok(None);
    }
    let client = match redis_client_from_env()? {
        Some(client) => client,
        None => return Ok(None),
    };
    let key = format!(
        "{}:llm:{}:{}:{}:{}",
        prefix, prompt_version, model_name, chosen_lang, url_hash
    );
    let mut connection = client.get_connection()?;
    let raw: Option<String> = connection.get(key)?;
    raw.map(|text| serde_json::from_str::<Value>(&text).map_err(ExecutionError::from))
        .transpose()
}

fn write_summary_cache(
    url_hash: &str,
    prompt_version: &str,
    model_name: &str,
    chosen_lang: &str,
    summary: &Value,
) -> Result<(), ExecutionError> {
    let prefix = env::var("REDIS_PREFIX").unwrap_or_else(|_| "bsr".to_string());
    let enabled =
        parse_bool_env("REDIS_ENABLED", true) && parse_bool_env("REDIS_CACHE_ENABLED", true);
    if !enabled {
        return Ok(());
    }
    let ttl = env::var("REDIS_LLM_TTL_SECONDS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(7_200);
    let client = match redis_client_from_env()? {
        Some(client) => client,
        None => return Ok(()),
    };
    let key = format!(
        "{}:llm:{}:{}:{}:{}",
        prefix, prompt_version, model_name, chosen_lang, url_hash
    );
    let payload = serde_json::to_string(summary)?;
    let mut connection = client.get_connection()?;
    let _: () = connection.set_ex(key, payload, ttl)?;
    Ok(())
}

fn redis_client_from_env() -> Result<Option<redis::Client>, ExecutionError> {
    let url = env::var("REDIS_URL")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| {
            let host = env::var("REDIS_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
            let port = env::var("REDIS_PORT").unwrap_or_else(|_| "6379".to_string());
            let db = env::var("REDIS_DB").unwrap_or_else(|_| "0".to_string());
            format!("redis://{host}:{port}/{db}")
        });
    Ok(Some(redis::Client::open(url)?))
}

pub fn write_ndjson_event(
    writer: &mut dyn Write,
    event: &OrchestratorEvent,
) -> Result<(), ExecutionError> {
    serde_json::to_writer(&mut *writer, event)?;
    writer.write_all(b"\n")?;
    writer.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        build_response_format, build_summary_messages, build_summary_requests,
        build_summary_user_content, clean_markdown_article_text, detect_low_value_content,
        ensure_summary_metadata, normalize_text, terminal_model, FirecrawlResult,
    };
    use bsr_worker::{WorkerAttemptOutput, WorkerExecutionOutput, WorkerLlmCallResult};

    #[test]
    fn summary_requests_preserve_schema_then_json_fallback_order() {
        let messages = build_summary_messages("sys", "user", &[]);
        let requests = build_summary_requests(
            &messages,
            "primary-model",
            "json_schema",
            &["fallback-model".to_string()],
            Some("flash-model"),
            &["flash-fallback-model".to_string()],
            0.2,
            Some(0.9),
            Some(0.15),
            Some(0.9),
            "body",
            "body",
        );

        assert_eq!(requests[0].preset_name.as_deref(), Some("schema_strict"));
        assert_eq!(
            requests[1].preset_name.as_deref(),
            Some("json_object_guardrail")
        );
        assert_eq!(
            requests[2].preset_name.as_deref(),
            Some("json_object_flash")
        );
        assert_eq!(
            requests[3].preset_name.as_deref(),
            Some("json_object_flash")
        );
        assert_eq!(
            requests[4].preset_name.as_deref(),
            Some("json_object_fallback")
        );
    }

    #[test]
    fn metadata_backfill_uses_crawl_metadata_and_canonical_url() {
        let summary = ensure_summary_metadata(
            json!({"summary_250": "short", "summary_1000": "long", "tldr": "full"}),
            Some("Article title"),
            Some("https://example.com/path"),
            Some(&json!({"author": "Jane", "published": "2026-03-12"})),
        );

        let metadata = summary
            .get("metadata")
            .and_then(|value| value.as_object())
            .expect("metadata object");
        assert_eq!(metadata.get("title"), Some(&json!("Article title")));
        assert_eq!(
            metadata.get("canonical_url"),
            Some(&json!("https://example.com/path"))
        );
        assert_eq!(metadata.get("domain"), Some(&json!("example.com")));
        assert_eq!(metadata.get("author"), Some(&json!("Jane")));
    }

    #[test]
    fn low_value_detection_flags_cookie_overlay() {
        let result = FirecrawlResult {
            status: "success".to_string(),
            http_status: Some(200),
            content_markdown: Some("cookie cookie accept cookies login subscribe".to_string()),
            content_html: None,
            structured_json: None,
            metadata_json: None,
            links_json: None,
            response_success: Some(true),
            response_error_code: None,
            response_error_message: None,
            response_details: None,
            latency_ms: Some(10),
            error_text: None,
            source_url: None,
            endpoint: None,
            options_json: None,
            correlation_id: None,
        };

        let low_value = detect_low_value_content(&result).expect("low-value payload");
        assert_eq!(
            low_value.get("reason"),
            Some(&json!("overlay_content_detected"))
        );
    }

    #[test]
    fn markdown_cleaner_drops_images_and_ui_lines() {
        let cleaned = clean_markdown_article_text(
            "Share\n\n![image](https://cdn.example.com/image.jpg)\n\n[Article](https://example.com)\n\nReal content.",
        );
        assert_eq!(cleaned, "Article\n\nReal content.");
    }

    #[test]
    fn normalize_text_removes_urls_and_collapses_spacing() {
        let normalized = normalize_text("Hello  https://example.com   world");
        assert_eq!(normalized, "Hello world");
    }

    #[test]
    fn terminal_model_uses_terminal_attempt_index() {
        let output = WorkerExecutionOutput {
            status: "ok".to_string(),
            summary: None,
            attempts: vec![
                WorkerAttemptOutput {
                    preset_name: None,
                    model_override: None,
                    llm_result: WorkerLlmCallResult {
                        status: "ok".to_string(),
                        model: Some("first".to_string()),
                        response_text: None,
                        response_json: None,
                        openrouter_response_text: None,
                        openrouter_response_json: None,
                        tokens_prompt: None,
                        tokens_completion: None,
                        cost_usd: None,
                        latency_ms: None,
                        error_text: None,
                        request_headers: None,
                        request_messages: None,
                        endpoint: "/api/v1/chat/completions".to_string(),
                        structured_output_used: true,
                        structured_output_mode: Some("json_object".to_string()),
                        error_context: None,
                    },
                },
                WorkerAttemptOutput {
                    preset_name: None,
                    model_override: None,
                    llm_result: WorkerLlmCallResult {
                        status: "ok".to_string(),
                        model: Some("terminal".to_string()),
                        response_text: None,
                        response_json: None,
                        openrouter_response_text: None,
                        openrouter_response_json: None,
                        tokens_prompt: None,
                        tokens_completion: None,
                        cost_usd: None,
                        latency_ms: None,
                        error_text: None,
                        request_headers: None,
                        request_messages: None,
                        endpoint: "/api/v1/chat/completions".to_string(),
                        structured_output_used: true,
                        structured_output_mode: Some("json_object".to_string()),
                        error_context: None,
                    },
                },
            ],
            terminal_attempt_index: Some(1),
            error_text: None,
        };

        assert_eq!(terminal_model(&output).as_deref(), Some("terminal"));
    }

    #[test]
    fn response_format_uses_json_schema_when_requested() {
        let format = build_response_format("json_schema");
        assert_eq!(format.get("type"), Some(&json!("json_schema")));
    }

    #[test]
    fn summary_user_content_appends_search_context_when_present() {
        let content = build_summary_user_content("content", "en", "SEARCH BLOCK");
        assert!(content.contains("SEARCH BLOCK"));
    }
}
