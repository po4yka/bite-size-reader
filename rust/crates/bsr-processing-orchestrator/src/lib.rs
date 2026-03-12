use bsr_pipeline_shadow::{
    build_chunk_sentence_plan_snapshot, build_chunking_preprocess_snapshot,
    build_llm_wrapper_plan_snapshot, ChunkSentencePlanInput, ChunkSentencePlanSnapshot,
    ChunkingPreprocessInput, LlmWrapperPlanInput, LlmWrapperPlanSnapshot,
};
use serde::{Deserialize, Serialize};

const LANG_EN: &str = "en";
const LANG_RU: &str = "ru";
const LANG_AUTO: &str = "auto";
const MAX_SINGLE_PASS_CHARS: usize = 50_000;
const MAX_FORWARD_CONTENT_CHARS: usize = 45_000;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UrlProcessingPlanInput {
    pub dedupe_hash: String,
    pub content_text: String,
    pub detected_language: String,
    pub preferred_language: String,
    pub silent: bool,
    pub enable_chunking: bool,
    pub configured_chunk_max_chars: usize,
    pub primary_model: String,
    pub long_context_model: Option<String>,
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
pub struct UrlProcessingPlan {
    pub flow_kind: String,
    pub dedupe_hash: String,
    pub detected_language: String,
    pub chosen_lang: String,
    pub needs_ru_translation: bool,
    pub content_length: usize,
    pub threshold_model: String,
    pub summary_strategy: String,
    pub summary_model: String,
    pub effective_max_chars: usize,
    pub chunk_plan: Option<ChunkSentencePlanSnapshot>,
    pub single_pass_request_plan: Option<LlmWrapperPlanSnapshot>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ForwardProcessingPlanInput {
    pub text: String,
    pub source_chat_title: Option<String>,
    pub source_user_first_name: Option<String>,
    pub source_user_last_name: Option<String>,
    pub forward_sender_name: Option<String>,
    pub preferred_language: String,
    pub primary_model: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ForwardProcessingPlan {
    pub flow_kind: String,
    pub source_label: String,
    pub source_title: String,
    pub prompt: String,
    pub llm_prompt: String,
    pub llm_prompt_truncated: bool,
    pub prompt_length: usize,
    pub detected_language: String,
    pub chosen_lang: String,
    pub summary_model: String,
    pub llm_max_tokens: i64,
}

pub fn build_url_processing_plan(input: &UrlProcessingPlanInput) -> UrlProcessingPlan {
    let detected_language = normalize_language(&input.detected_language);
    let chosen_lang = choose_language(&input.preferred_language, &detected_language);
    let needs_ru_translation =
        !input.silent && chosen_lang != LANG_RU && detected_language != LANG_RU;

    let threshold_model = normalize_model(
        input
            .long_context_model
            .as_deref()
            .unwrap_or(input.primary_model.as_str()),
    );
    let tuned_base = ((input.configured_chunk_max_chars.max(1) as f64) * 0.8_f64).floor() as usize;
    let effective_max_chars = estimate_max_chars_for_model(&threshold_model, tuned_base.max(1));

    let chunking = build_chunking_preprocess_snapshot(&ChunkingPreprocessInput {
        content_text: input.content_text.clone(),
        enable_chunking: input.enable_chunking,
        max_chars: effective_max_chars,
        long_context_model: normalize_optional_model(input.long_context_model.as_deref()),
    });

    let chunk_plan = if chunking.should_chunk {
        Some(build_chunk_sentence_plan_snapshot(
            &ChunkSentencePlanInput {
                content_text: input.content_text.clone(),
                lang: chosen_lang.clone(),
                max_chars: chunking.max_chars,
            },
        ))
    } else {
        None
    };

    let is_chunked = chunk_plan
        .as_ref()
        .map(|plan| !plan.chunks.is_empty())
        .unwrap_or(false);
    let summary_strategy = if is_chunked { "chunked" } else { "single_pass" }.to_string();

    let summary_model = if !is_chunked && input.content_text.chars().count() > MAX_SINGLE_PASS_CHARS
    {
        normalize_optional_model(input.long_context_model.as_deref())
            .unwrap_or_else(|| normalize_model(&input.primary_model))
    } else {
        normalize_model(&input.primary_model)
    };

    let single_pass_request_plan = if is_chunked {
        None
    } else {
        Some(build_llm_wrapper_plan_snapshot(&LlmWrapperPlanInput {
            base_model: summary_model.clone(),
            schema_response_type: normalize_response_type(&input.schema_response_type),
            json_object_response_type: normalize_response_type(&input.json_object_response_type),
            max_tokens_schema: input.max_tokens_schema,
            max_tokens_json_object: input.max_tokens_json_object,
            base_temperature: input.base_temperature,
            base_top_p: input.base_top_p,
            json_temperature: input.json_temperature,
            json_top_p: input.json_top_p,
            fallback_models: input
                .fallback_models
                .iter()
                .map(|model| normalize_model(model))
                .filter(|model| !model.is_empty())
                .collect(),
            flash_model: normalize_optional_model(input.flash_model.as_deref()),
            flash_fallback_models: input
                .flash_fallback_models
                .iter()
                .map(|model| normalize_model(model))
                .filter(|model| !model.is_empty())
                .collect(),
        }))
    };

    UrlProcessingPlan {
        flow_kind: "url".to_string(),
        dedupe_hash: input.dedupe_hash.clone(),
        detected_language,
        chosen_lang,
        needs_ru_translation,
        content_length: input.content_text.chars().count(),
        threshold_model,
        summary_strategy,
        summary_model,
        effective_max_chars: chunking.max_chars,
        chunk_plan,
        single_pass_request_plan,
    }
}

pub fn build_forward_processing_plan(input: &ForwardProcessingPlanInput) -> ForwardProcessingPlan {
    let detected_language = detect_language(&input.text);
    let chosen_lang = choose_language(&input.preferred_language, &detected_language);
    let (source_label, source_title) = resolve_forward_source(input);
    let prompt = if source_title.is_empty() {
        input.text.clone()
    } else {
        format!("{source_label}: {source_title}\n\n{}", input.text)
    };
    let prompt_length = prompt.chars().count();

    let (llm_prompt, llm_prompt_truncated) = truncate_forward_prompt(&prompt);
    let llm_max_tokens = (llm_prompt.chars().count() / 4 + 2_048).clamp(2_048, 6_144) as i64;

    ForwardProcessingPlan {
        flow_kind: "forward".to_string(),
        source_label,
        source_title,
        prompt,
        llm_prompt,
        llm_prompt_truncated,
        prompt_length,
        detected_language,
        chosen_lang,
        summary_model: normalize_model(&input.primary_model),
        llm_max_tokens,
    }
}

fn resolve_forward_source(input: &ForwardProcessingPlanInput) -> (String, String) {
    let source_title = normalize_text(input.source_chat_title.as_deref())
        .or_else(|| {
            let first = normalize_text(input.source_user_first_name.as_deref()).unwrap_or_default();
            let last = normalize_text(input.source_user_last_name.as_deref()).unwrap_or_default();
            let full_name = format!("{first} {last}").trim().to_string();
            (!full_name.is_empty()).then_some(full_name)
        })
        .or_else(|| normalize_text(input.forward_sender_name.as_deref()))
        .unwrap_or_default();

    let source_label = if normalize_text(input.source_chat_title.as_deref()).is_some() {
        "Channel".to_string()
    } else {
        "Source".to_string()
    };

    (source_label, source_title)
}

fn truncate_forward_prompt(prompt: &str) -> (String, bool) {
    let prompt_length = prompt.chars().count();
    if prompt_length <= MAX_FORWARD_CONTENT_CHARS {
        return (prompt.to_string(), false);
    }

    let truncated = prompt
        .char_indices()
        .nth(MAX_FORWARD_CONTENT_CHARS)
        .map(|(idx, _)| prompt[..idx].to_string())
        .unwrap_or_else(|| prompt.to_string());

    (
        format!("{truncated}\n\n[Content truncated due to length]"),
        true,
    )
}

fn detect_language(text: &str) -> String {
    if text
        .chars()
        .any(|ch| ('\u{0400}'..='\u{04FF}').contains(&ch))
    {
        LANG_RU.to_string()
    } else {
        LANG_EN.to_string()
    }
}

fn choose_language(preferred: &str, detected: &str) -> String {
    let preferred = normalize_language(preferred);
    let detected = normalize_language(detected);
    if matches!(preferred.as_str(), LANG_EN | LANG_RU) {
        preferred
    } else if matches!(detected.as_str(), LANG_EN | LANG_RU) {
        detected
    } else {
        LANG_EN.to_string()
    }
}

fn normalize_language(value: &str) -> String {
    let normalized = value.trim().to_lowercase();
    if normalized.is_empty() {
        return LANG_EN.to_string();
    }
    match normalized.as_str() {
        LANG_EN | LANG_RU | LANG_AUTO => normalized,
        _ => LANG_EN.to_string(),
    }
}

fn normalize_response_type(value: &str) -> String {
    let normalized = value.trim().to_lowercase();
    if normalized.is_empty() {
        "unknown".to_string()
    } else {
        normalized
    }
}

fn normalize_model(value: &str) -> String {
    value.trim().to_string()
}

fn normalize_optional_model(value: Option<&str>) -> Option<String> {
    value.map(normalize_model).filter(|value| !value.is_empty())
}

fn normalize_text(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToString::to_string)
}

fn estimate_max_chars_for_model(model_name: &str, base_default: usize) -> usize {
    if model_name.is_empty() {
        return base_default;
    }

    let lower = model_name.to_lowercase();
    if lower.contains("gemini-2.5") || lower.contains("2.5-pro") || lower.contains("gemini-2-5") {
        return ((1_000_000_f64 * 4_f64) * 0.75_f64) as usize;
    }

    base_default
}

#[cfg(test)]
mod tests {
    use super::{
        build_forward_processing_plan, build_url_processing_plan, ForwardProcessingPlanInput,
        UrlProcessingPlanInput,
    };

    #[test]
    fn url_processing_plan_uses_chunked_strategy_without_long_context() {
        let plan = build_url_processing_plan(&UrlProcessingPlanInput {
            dedupe_hash: "hash".to_string(),
            content_text: "Sentence one. Sentence two. Sentence three. ".repeat(4_000),
            detected_language: "en".to_string(),
            preferred_language: "auto".to_string(),
            silent: false,
            enable_chunking: true,
            configured_chunk_max_chars: 20_000,
            primary_model: "openrouter/base-model".to_string(),
            long_context_model: None,
            schema_response_type: "json_schema".to_string(),
            json_object_response_type: "json_object".to_string(),
            max_tokens_schema: Some(2_048),
            max_tokens_json_object: Some(2_048),
            base_temperature: Some(0.2),
            base_top_p: Some(0.9),
            json_temperature: Some(0.15),
            json_top_p: Some(0.9),
            fallback_models: vec!["openrouter/fallback".to_string()],
            flash_model: None,
            flash_fallback_models: vec![],
        });

        assert_eq!(plan.flow_kind, "url");
        assert_eq!(plan.chosen_lang, "en");
        assert_eq!(plan.summary_strategy, "chunked");
        assert!(plan.chunk_plan.is_some());
        assert!(plan.single_pass_request_plan.is_none());
    }

    #[test]
    fn url_processing_plan_uses_long_context_model_for_large_single_pass() {
        let plan = build_url_processing_plan(&UrlProcessingPlanInput {
            dedupe_hash: "hash".to_string(),
            content_text: "x".repeat(70_000),
            detected_language: "en".to_string(),
            preferred_language: "ru".to_string(),
            silent: false,
            enable_chunking: true,
            configured_chunk_max_chars: 20_000,
            primary_model: "openrouter/base-model".to_string(),
            long_context_model: Some("google/gemini-2.5-pro".to_string()),
            schema_response_type: "json_schema".to_string(),
            json_object_response_type: "json_object".to_string(),
            max_tokens_schema: Some(2_048),
            max_tokens_json_object: Some(2_048),
            base_temperature: Some(0.2),
            base_top_p: Some(0.9),
            json_temperature: Some(0.15),
            json_top_p: Some(0.9),
            fallback_models: vec!["openrouter/fallback".to_string()],
            flash_model: Some("google/gemini-3-flash-preview".to_string()),
            flash_fallback_models: vec![],
        });

        assert_eq!(plan.chosen_lang, "ru");
        assert!(!plan.needs_ru_translation);
        assert_eq!(plan.summary_strategy, "single_pass");
        assert_eq!(plan.summary_model, "google/gemini-2.5-pro");
        assert!(plan.single_pass_request_plan.is_some());
    }

    #[test]
    fn forward_processing_plan_builds_channel_prompt_and_truncation_metadata() {
        let plan = build_forward_processing_plan(&ForwardProcessingPlanInput {
            text: "x".repeat(46_000),
            source_chat_title: Some("Channel title".to_string()),
            source_user_first_name: None,
            source_user_last_name: None,
            forward_sender_name: None,
            preferred_language: "auto".to_string(),
            primary_model: "openrouter/base-model".to_string(),
        });

        assert_eq!(plan.flow_kind, "forward");
        assert_eq!(plan.source_label, "Channel");
        assert_eq!(plan.source_title, "Channel title");
        assert!(plan.prompt.starts_with("Channel: Channel title"));
        assert!(plan.llm_prompt_truncated);
        assert!(plan
            .llm_prompt
            .contains("[Content truncated due to length]"));
        assert_eq!(plan.summary_model, "openrouter/base-model");
    }
}
