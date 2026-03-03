use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum PipelineShadowError {
    #[error("unsupported slice: {0}")]
    UnsupportedSlice(String),
    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExtractionAdapterInput {
    pub url_hash: String,
    pub content_text: String,
    pub content_source: Option<String>,
    pub title: Option<String>,
    pub images_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExtractionAdapterSnapshot {
    pub url_hash: String,
    pub content_length: usize,
    pub word_count: usize,
    pub content_source: String,
    pub title_present: bool,
    pub images_count: usize,
    pub has_media: bool,
    pub language_hint: String,
    pub content_fingerprint: String,
    pub low_value: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChunkingPreprocessInput {
    pub content_text: String,
    pub enable_chunking: bool,
    pub max_chars: usize,
    pub long_context_model: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChunkingPreprocessSnapshot {
    pub content_length: usize,
    pub max_chars: usize,
    pub chunk_size: usize,
    pub should_chunk: bool,
    pub long_context_bypass: bool,
    pub estimated_chunk_count: usize,
    pub first_chunk_size: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LlmWrapperPlanInput {
    pub base_model: String,
    pub schema_response_type: String,
    pub json_object_response_type: String,
    pub max_tokens_schema: Option<i64>,
    pub max_tokens_json_object: Option<i64>,
    pub base_temperature: Option<f64>,
    pub base_top_p: Option<f64>,
    pub json_temperature: Option<f64>,
    pub json_top_p: Option<f64>,
    pub fallback_models: Vec<String>,
    pub flash_model: Option<String>,
    pub flash_fallback_models: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LlmRequestPlan {
    pub preset: String,
    pub model: String,
    pub response_type: String,
    pub max_tokens: Option<i64>,
    pub temperature: Option<f64>,
    pub top_p: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LlmWrapperPlanSnapshot {
    pub request_count: usize,
    pub requests: Vec<LlmRequestPlan>,
}

pub fn build_extraction_adapter_snapshot(
    input: &ExtractionAdapterInput,
) -> ExtractionAdapterSnapshot {
    let content_trimmed = input.content_text.trim();
    let content_length = content_trimmed.chars().count();
    let word_count = content_trimmed.split_whitespace().count();
    let title_present = input
        .title
        .as_ref()
        .map(|title| !title.trim().is_empty())
        .unwrap_or(false);
    let content_source = input
        .content_source
        .as_ref()
        .map(|source| source.trim().to_lowercase())
        .filter(|source| !source.is_empty())
        .unwrap_or_else(|| "unknown".to_string());
    let has_media = input.images_count > 0;

    let language_hint = detect_language_hint(content_trimmed);
    let content_fingerprint = content_fingerprint(content_trimmed);
    let low_value = content_length < 120 || word_count < 20;

    ExtractionAdapterSnapshot {
        url_hash: input.url_hash.clone(),
        content_length,
        word_count,
        content_source,
        title_present,
        images_count: input.images_count,
        has_media,
        language_hint,
        content_fingerprint,
        low_value,
    }
}

pub fn build_chunking_preprocess_snapshot(
    input: &ChunkingPreprocessInput,
) -> ChunkingPreprocessSnapshot {
    let content_length = input.content_text.chars().count();
    let max_chars = input.max_chars.max(1);
    let chunk_size = (max_chars / 10).clamp(4_000, 12_000);

    let chunk_candidate = input.enable_chunking && content_length > max_chars;
    let long_context_bypass = chunk_candidate
        && input
            .long_context_model
            .as_ref()
            .map(|model| !model.trim().is_empty())
            .unwrap_or(false);
    let should_chunk = chunk_candidate && !long_context_bypass;

    let estimated_chunk_count = if should_chunk {
        content_length.div_ceil(chunk_size)
    } else {
        0
    };
    let first_chunk_size = if should_chunk {
        content_length.min(chunk_size)
    } else {
        0
    };

    ChunkingPreprocessSnapshot {
        content_length,
        max_chars,
        chunk_size,
        should_chunk,
        long_context_bypass,
        estimated_chunk_count,
        first_chunk_size,
    }
}

pub fn build_llm_wrapper_plan_snapshot(input: &LlmWrapperPlanInput) -> LlmWrapperPlanSnapshot {
    let mut requests = Vec::new();

    requests.push(LlmRequestPlan {
        preset: "schema_strict".to_string(),
        model: input.base_model.clone(),
        response_type: input.schema_response_type.clone(),
        max_tokens: input.max_tokens_schema,
        temperature: input.base_temperature,
        top_p: input.base_top_p,
    });
    requests.push(LlmRequestPlan {
        preset: "json_object_guardrail".to_string(),
        model: input.base_model.clone(),
        response_type: input.json_object_response_type.clone(),
        max_tokens: input.max_tokens_json_object,
        temperature: input.json_temperature,
        top_p: input.json_top_p,
    });

    let mut added_flash_models = std::collections::HashSet::new();
    let mut flash_candidates = Vec::new();
    if let Some(flash) = &input.flash_model {
        flash_candidates.push(flash.clone());
    }
    flash_candidates.extend(input.flash_fallback_models.clone());

    for model in flash_candidates {
        if model.trim().is_empty()
            || model == input.base_model
            || added_flash_models.contains(&model)
        {
            continue;
        }
        requests.push(LlmRequestPlan {
            preset: "json_object_flash".to_string(),
            model: model.clone(),
            response_type: input.json_object_response_type.clone(),
            max_tokens: input.max_tokens_json_object,
            temperature: input.json_temperature,
            top_p: input.json_top_p,
        });
        added_flash_models.insert(model);
    }

    let fallback_model = input
        .fallback_models
        .iter()
        .find(|model| !model.trim().is_empty() && *model != &input.base_model);

    if let Some(model) = fallback_model {
        if !added_flash_models.contains(model) {
            requests.push(LlmRequestPlan {
                preset: "json_object_fallback".to_string(),
                model: model.clone(),
                response_type: input.json_object_response_type.clone(),
                max_tokens: input.max_tokens_json_object,
                temperature: input.json_temperature,
                top_p: input.json_top_p,
            });
        }
    }

    let request_count = requests.len();
    LlmWrapperPlanSnapshot {
        request_count,
        requests,
    }
}

fn detect_language_hint(content: &str) -> String {
    let mut cyrillic = 0usize;
    let mut latin = 0usize;

    for ch in content.chars() {
        if ('\u{0400}'..='\u{04FF}').contains(&ch) {
            cyrillic += 1;
        } else if ch.is_ascii_alphabetic() {
            latin += 1;
        }
    }

    if cyrillic == 0 && latin == 0 {
        return "unknown".to_string();
    }
    if cyrillic as f64 > (latin as f64 * 1.2) {
        return "ru".to_string();
    }
    "en".to_string()
}

fn content_fingerprint(content: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    let digest = hasher.finalize();
    let hex = format!("{digest:x}");
    hex.chars().take(16).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extraction_adapter_snapshot_is_deterministic() {
        let input = ExtractionAdapterInput {
            url_hash: "abc123".to_string(),
            content_text: "Hello world from Rust pipeline shadow.".to_string(),
            content_source: Some("Markdown".to_string()),
            title: Some("Demo".to_string()),
            images_count: 1,
        };

        let snapshot = build_extraction_adapter_snapshot(&input);
        assert_eq!(snapshot.url_hash, "abc123");
        assert_eq!(snapshot.content_source, "markdown");
        assert!(snapshot.title_present);
        assert!(snapshot.has_media);
        assert_eq!(snapshot.language_hint, "en");
        assert_eq!(snapshot.content_fingerprint.len(), 16);
    }

    #[test]
    fn chunking_preprocess_snapshot_handles_bypass() {
        let input = ChunkingPreprocessInput {
            content_text: "x".repeat(12_000),
            enable_chunking: true,
            max_chars: 8_000,
            long_context_model: Some("moonshotai/kimi-k2.5".to_string()),
        };

        let snapshot = build_chunking_preprocess_snapshot(&input);
        assert!(snapshot.long_context_bypass);
        assert!(!snapshot.should_chunk);
        assert_eq!(snapshot.estimated_chunk_count, 0);
    }

    #[test]
    fn llm_wrapper_plan_snapshot_orders_requests() {
        let input = LlmWrapperPlanInput {
            base_model: "base/model".to_string(),
            schema_response_type: "json_schema".to_string(),
            json_object_response_type: "json_object".to_string(),
            max_tokens_schema: Some(4096),
            max_tokens_json_object: Some(4096),
            base_temperature: Some(0.2),
            base_top_p: Some(0.9),
            json_temperature: Some(0.1),
            json_top_p: Some(0.9),
            fallback_models: vec!["fallback/model".to_string()],
            flash_model: Some("flash/model".to_string()),
            flash_fallback_models: vec!["flash/other".to_string()],
        };

        let snapshot = build_llm_wrapper_plan_snapshot(&input);
        assert_eq!(snapshot.request_count, 5);
        assert_eq!(snapshot.requests[0].preset, "schema_strict");
        assert_eq!(snapshot.requests[1].preset, "json_object_guardrail");
        assert!(snapshot
            .requests
            .iter()
            .any(|req| req.preset == "json_object_fallback"));
    }
}
