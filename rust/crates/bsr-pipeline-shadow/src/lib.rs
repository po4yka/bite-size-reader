use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Number, Value};
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChunkSentencePlanInput {
    pub content_text: String,
    pub lang: String,
    pub max_chars: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChunkSentencePlanSnapshot {
    pub lang: String,
    pub max_chars: usize,
    pub chunk_size: usize,
    pub sentences: Vec<String>,
    pub chunks: Vec<String>,
    pub chunk_count: usize,
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContentCleanerInput {
    pub content_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContentCleanerSnapshot {
    pub content_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SummaryAggregateInput {
    pub summaries: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ChunkSynthesisPromptInput {
    pub aggregated: Value,
    pub chosen_lang: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ChunkSynthesisPromptSnapshot {
    pub context_text: String,
    pub user_content: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SummaryUserContentInput {
    pub content_for_summary: String,
    pub chosen_lang: String,
    pub search_context: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SummaryUserContentSnapshot {
    pub content_hint: String,
    pub user_content: String,
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

pub fn build_chunk_sentence_plan_snapshot(
    input: &ChunkSentencePlanInput,
) -> ChunkSentencePlanSnapshot {
    let max_chars = input.max_chars.max(1);
    let chunk_size = (max_chars / 10).clamp(4_000, 12_000).min(max_chars);
    let lang = if input.lang.trim().eq_ignore_ascii_case("ru") {
        "ru".to_string()
    } else {
        "en".to_string()
    };
    let sentences = split_sentences_for_chunking(&input.content_text, &lang);
    let chunks = chunk_sentences_for_chunking(&sentences, chunk_size);
    let chunk_count = chunks.len();
    let first_chunk_size = chunks
        .first()
        .map(|chunk| chunk.chars().count())
        .unwrap_or(0);

    ChunkSentencePlanSnapshot {
        lang,
        max_chars,
        chunk_size,
        sentences,
        chunks,
        chunk_count,
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

pub fn build_content_cleaner_snapshot(input: &ContentCleanerInput) -> ContentCleanerSnapshot {
    ContentCleanerSnapshot {
        content_text: clean_content_for_llm(&input.content_text),
    }
}

pub fn build_summary_aggregate_snapshot(input: &SummaryAggregateInput) -> Value {
    aggregate_chunk_summaries(&input.summaries)
}

pub fn build_chunk_synthesis_prompt_snapshot(
    input: &ChunkSynthesisPromptInput,
) -> ChunkSynthesisPromptSnapshot {
    let aggregated = input.aggregated.as_object();
    let tldr = aggregated
        .and_then(|obj| obj.get("tldr"))
        .map(stringify_like_python)
        .unwrap_or_default();
    let summary_250 = aggregated
        .and_then(|obj| obj.get("summary_250"))
        .map(stringify_like_python)
        .unwrap_or_default();
    let key_ideas_json = aggregated
        .and_then(|obj| obj.get("key_ideas"))
        .map(python_json_dumps_value)
        .unwrap_or_else(|| "[]".to_string());

    let context_text = format!(
        "TLDR DRAFT:\n{tldr}\n\nDETAILED SUMMARY DRAFT:\n{summary_250}\n\nKEY IDEAS DRAFT:\n{key_ideas_json}"
    );
    let response_language = if input.chosen_lang.trim().eq_ignore_ascii_case("ru") {
        "Russian"
    } else {
        "English"
    };
    let user_content = format!(
        "Synthesize the following draft summaries (generated from article chunks) into a single, cohesive, high-quality summary. Ensure the flow is natural and redundant information is removed. Output ONLY a valid JSON object matching the schema.\nRespond in {response_language}.\n\nDRAFT CONTENT START\n{context_text}\nDRAFT CONTENT END"
    );
    ChunkSynthesisPromptSnapshot {
        context_text,
        user_content,
    }
}

pub fn build_summary_user_content_snapshot(
    input: &SummaryUserContentInput,
) -> SummaryUserContentSnapshot {
    let content_hint = detect_summary_content_type_hint(&input.content_for_summary);
    let response_language = if input.chosen_lang == "ru" {
        "Russian"
    } else {
        "English"
    };

    let mut user_content = format!(
        "Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. Respond in {response_language}. Do NOT include any text outside the JSON.\n\n{content_hint}CONTENT START\n{}\nCONTENT END",
        input.content_for_summary
    );
    if !input.search_context.is_empty() {
        user_content.push_str("\n\n");
        user_content.push_str(&input.search_context);
    }

    SummaryUserContentSnapshot {
        content_hint,
        user_content,
    }
}

pub fn clean_content_for_llm(text: &str) -> String {
    if text.trim().is_empty() {
        return text.to_string();
    }

    let mut out = text.to_string();
    out = collapse_whitespace(&out);
    out = strip_markdown_link_urls(&out);
    out = remove_boilerplate_sections(&out);
    out = remove_repeated_nav_items(&out, 3);
    out = truncate_after_comments(&out);
    out.trim().to_string()
}

fn collapse_whitespace(text: &str) -> String {
    static BLANK_LINES: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"\n{3,}").expect("valid blank-line regex"));
    BLANK_LINES.replace_all(text, "\n\n").to_string()
}

fn strip_markdown_link_urls(text: &str) -> String {
    static MD_LINK: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"\[([^\]]+)\]\([^)]+\)").expect("valid markdown-link regex"));
    MD_LINK.replace_all(text, "$1").to_string()
}

fn remove_boilerplate_sections(text: &str) -> String {
    static BOILERPLATE_HEADING: Lazy<Regex> = Lazy::new(|| {
        Regex::new(
            r"(?i)^#{1,4}\s*(?:related\s+(?:articles?|posts?|stories?|content|links?|reads?)|you\s+(?:may|might|could)\s+(?:also\s+)?(?:like|enjoy|read)|(?:more|other|similar)\s+(?:articles?|posts?|stories?|reads?)|(?:comments?|leave\s+a\s+(?:reply|comment))|(?:share\s+this|subscribe|newsletter|sign\s*up)|(?:advertisement|sponsored|promoted)|(?:footer|sidebar|navigation|breadcrumb))\s*$",
        )
        .expect("valid boilerplate-heading regex")
    });
    static HEADING_START: Lazy<Regex> =
        Lazy::new(|| Regex::new(r"^#{1,4}\s+\S").expect("valid heading-start regex"));

    let mut skipping = false;
    let mut result: Vec<&str> = Vec::new();

    for line in text.split('\n') {
        if BOILERPLATE_HEADING.is_match(line.trim()) {
            skipping = true;
            continue;
        }
        if skipping && HEADING_START.is_match(line) {
            skipping = false;
        }
        if !skipping {
            result.push(line);
        }
    }

    result.join("\n")
}

fn remove_repeated_nav_items(text: &str, threshold: usize) -> String {
    use std::collections::{HashMap, HashSet};

    let mut counter: HashMap<String, usize> = HashMap::new();
    let lines: Vec<&str> = text.split('\n').collect();

    for line in &lines {
        let stripped = line.trim();
        if stripped.is_empty() {
            continue;
        }
        *counter.entry(stripped.to_string()).or_insert(0) += 1;
    }

    let repeated: HashSet<String> = counter
        .into_iter()
        .filter_map(|(line, count)| (count >= threshold).then_some(line))
        .collect();
    if repeated.is_empty() {
        return text.to_string();
    }

    let kept: Vec<&str> = lines
        .iter()
        .copied()
        .filter(|line| !repeated.contains(line.trim()))
        .collect();
    kept.join("\n")
}

fn truncate_after_comments(text: &str) -> String {
    static COMMENT_MARKER: Lazy<Regex> = Lazy::new(|| {
        Regex::new(
            r"(?im)^(?:#{1,4}\s+)?(?:\d+\s+)?(?:comments?|responses?|replies?|discussion)\s*$",
        )
        .expect("valid comments-marker regex")
    });
    if let Some(m) = COMMENT_MARKER.find(text) {
        return text[..m.start()].trim_end().to_string();
    }
    text.to_string()
}

fn split_sentences_for_chunking(text: &str, _lang: &str) -> Vec<String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }

    let mut out: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut chars = trimmed.chars().peekable();

    while let Some(ch) = chars.next() {
        current.push(ch);
        if matches!(ch, '.' | '!' | '?') {
            let mut consumed_whitespace = false;
            while let Some(next) = chars.peek().copied() {
                if next.is_whitespace() {
                    consumed_whitespace = true;
                    current.push(next);
                    chars.next();
                } else {
                    break;
                }
            }
            if consumed_whitespace {
                let sentence = current.trim();
                if !sentence.is_empty() {
                    out.push(sentence.to_string());
                }
                current.clear();
            }
        }
    }

    let tail = current.trim();
    if !tail.is_empty() {
        out.push(tail.to_string());
    }
    out
}

fn chunk_sentences_for_chunking(sentences: &[String], max_chars: usize) -> Vec<String> {
    let mut chunks: Vec<String> = Vec::new();
    let mut buf: Vec<String> = Vec::new();
    let mut size = 0usize;

    for sentence in sentences {
        let stripped = sentence.trim();
        if stripped.is_empty() {
            continue;
        }

        let sentence_len = stripped.chars().count();
        let extra = if buf.is_empty() { 0 } else { 1 };
        if size + sentence_len + extra > max_chars && !buf.is_empty() {
            chunks.push(buf.join(" "));
            buf = vec![stripped.to_string()];
            size = sentence_len;
        } else {
            if !buf.is_empty() {
                size += 1;
            }
            buf.push(stripped.to_string());
            size += sentence_len;
        }
    }

    if !buf.is_empty() {
        chunks.push(buf.join(" "));
    }
    chunks
}

fn aggregate_chunk_summaries(summaries: &[Value]) -> Value {
    if summaries.is_empty() {
        return empty_summary_payload();
    }

    let mut s250_parts: Vec<String> = Vec::new();
    let mut s1000_parts: Vec<String> = Vec::new();
    let mut tldr_parts: Vec<String> = Vec::new();
    let mut key_ideas: Vec<String> = Vec::new();
    let mut topic_tags: Vec<String> = Vec::new();
    let mut entity_people: Vec<String> = Vec::new();
    let mut entity_organizations: Vec<String> = Vec::new();
    let mut entity_locations: Vec<String> = Vec::new();
    let mut ert_sum: i64 = 0;
    let mut key_stats: Vec<Value> = Vec::new();
    let mut answered: Vec<String> = Vec::new();
    let mut seo_keywords: Vec<String> = Vec::new();
    let mut topic_overview_parts: Vec<String> = Vec::new();
    let mut caution_parts: Vec<String> = Vec::new();
    let mut new_facts: Vec<Value> = Vec::new();
    let mut fact_keys: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut open_questions: Vec<String> = Vec::new();
    let mut suggested_sources: Vec<String> = Vec::new();
    let mut expansion_topics: Vec<String> = Vec::new();
    let mut next_exploration: Vec<String> = Vec::new();

    for summary in summaries {
        let Some(summary_obj) = summary.as_object() else {
            continue;
        };

        let s250 = summary_obj
            .get("summary_250")
            .map(stringify_like_python)
            .unwrap_or_default()
            .trim()
            .to_string();
        if !s250.is_empty() {
            s250_parts.push(s250);
        }

        let s1000_seed = pick_or_value(summary_obj.get("summary_1000"), summary_obj.get("tldr"));
        let s1000_value = s1000_seed
            .map(stringify_like_python)
            .unwrap_or_default()
            .trim()
            .to_string();
        if !s1000_value.is_empty() {
            s1000_parts.push(s1000_value.clone());
        }

        let tldr_seed = if summary_obj.get("tldr").is_some_and(python_truthy_value) {
            summary_obj.get("tldr")
        } else {
            None
        };
        let tldr_value = if let Some(value) = tldr_seed {
            stringify_like_python(value).trim().to_string()
        } else {
            s1000_value.clone()
        };
        if !tldr_value.is_empty() {
            tldr_parts.push(tldr_value);
        }

        key_ideas.extend(read_string_list(summary_obj.get("key_ideas"), false));
        topic_tags.extend(read_string_list(summary_obj.get("topic_tags"), false));
        answered.extend(read_string_list(
            summary_obj.get("answered_questions"),
            false,
        ));
        seo_keywords.extend(read_string_list(summary_obj.get("seo_keywords"), false));

        if let Some(entities) = summary_obj.get("entities").and_then(Value::as_object) {
            entity_people.extend(read_string_list(entities.get("people"), false));
            entity_organizations.extend(read_string_list(entities.get("organizations"), false));
            entity_locations.extend(read_string_list(entities.get("locations"), false));
        }

        if let Some(ert) = parse_python_int(summary_obj.get("estimated_reading_time_min")) {
            ert_sum += ert;
        }

        key_stats = merge_key_stats(&key_stats, summary_obj.get("key_stats"), 20);

        if let Some(insights_obj) = summary_obj.get("insights").and_then(Value::as_object) {
            let overview = insights_obj
                .get("topic_overview")
                .map(stringify_like_python)
                .unwrap_or_default()
                .trim()
                .to_string();
            if !overview.is_empty() {
                topic_overview_parts.push(overview);
            }

            let caution = insights_obj
                .get("caution")
                .map(stringify_like_python)
                .unwrap_or_default()
                .trim()
                .to_string();
            if !caution.is_empty() {
                caution_parts.push(caution);
            }

            if let Some(Value::Array(facts)) = insights_obj.get("new_facts") {
                for fact in facts {
                    let Some(fact_obj) = fact.as_object() else {
                        continue;
                    };
                    let fact_text = fact_obj
                        .get("fact")
                        .map(stringify_like_python)
                        .unwrap_or_default()
                        .trim()
                        .to_string();
                    if fact_text.is_empty() {
                        continue;
                    }
                    let fact_key = fact_text.to_lowercase();
                    if fact_keys.contains(&fact_key) {
                        continue;
                    }
                    fact_keys.insert(fact_key);

                    let why = fact_obj
                        .get("why_it_matters")
                        .map(stringify_like_python)
                        .unwrap_or_default()
                        .trim()
                        .to_string();
                    let source_hint = fact_obj
                        .get("source_hint")
                        .map(stringify_like_python)
                        .unwrap_or_default()
                        .trim()
                        .to_string();

                    let mut fact_entry = serde_json::Map::new();
                    fact_entry.insert("fact".to_string(), Value::String(fact_text));
                    fact_entry.insert(
                        "why_it_matters".to_string(),
                        if why.is_empty() {
                            Value::Null
                        } else {
                            Value::String(why)
                        },
                    );
                    fact_entry.insert(
                        "source_hint".to_string(),
                        if source_hint.is_empty() {
                            Value::Null
                        } else {
                            Value::String(source_hint)
                        },
                    );
                    fact_entry.insert(
                        "confidence".to_string(),
                        fact_obj.get("confidence").cloned().unwrap_or(Value::Null),
                    );
                    new_facts.push(Value::Object(fact_entry));
                }
            }

            open_questions.extend(read_string_list(insights_obj.get("open_questions"), true));
            suggested_sources.extend(read_string_list(
                insights_obj.get("suggested_sources"),
                true,
            ));
            expansion_topics.extend(read_string_list(insights_obj.get("expansion_topics"), true));
            next_exploration.extend(read_string_list(insights_obj.get("next_exploration"), true));
        }
    }

    let s250_joined = select_best_summary_250(&s250_parts);
    let s1000_joined = dedupe_sentences(&dedupe_list(&s1000_parts, None));
    let mut tldr_joined = dedupe_sentences(&dedupe_list(&tldr_parts, None));
    if !tldr_joined.is_empty()
        && !s1000_joined.is_empty()
        && tldr_joined.chars().count() <= s1000_joined.chars().count()
    {
        tldr_joined = format!("{s1000_joined} {tldr_joined}");
    }

    let topic_overview = dedupe_list(&topic_overview_parts, Some(3)).join("\n\n");
    let caution_joined = dedupe_list(&caution_parts, Some(2)).join("\n\n");

    let summary_1000 = if !s1000_joined.is_empty() {
        s1000_joined.clone()
    } else if !tldr_joined.is_empty() {
        tldr_joined.clone()
    } else {
        s250_joined.clone()
    };
    let tldr = if !tldr_joined.is_empty() {
        tldr_joined.clone()
    } else if !s1000_joined.is_empty() {
        s1000_joined.clone()
    } else {
        s250_joined.clone()
    };

    let mut insights = serde_json::Map::new();
    insights.insert("topic_overview".to_string(), Value::String(topic_overview));
    insights.insert(
        "new_facts".to_string(),
        Value::Array(new_facts.into_iter().take(8).collect()),
    );
    insights.insert(
        "open_questions".to_string(),
        Value::Array(
            dedupe_list(&open_questions, Some(6))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    insights.insert(
        "suggested_sources".to_string(),
        Value::Array(
            dedupe_list(&suggested_sources, Some(6))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    insights.insert(
        "expansion_topics".to_string(),
        Value::Array(
            dedupe_list(&expansion_topics, Some(6))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    insights.insert(
        "next_exploration".to_string(),
        Value::Array(
            dedupe_list(&next_exploration, Some(6))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    insights.insert(
        "caution".to_string(),
        if caution_joined.is_empty() {
            Value::Null
        } else {
            Value::String(caution_joined)
        },
    );

    let mut entities = serde_json::Map::new();
    entities.insert(
        "people".to_string(),
        Value::Array(
            dedupe_list(&entity_people, None)
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    entities.insert(
        "organizations".to_string(),
        Value::Array(
            dedupe_list(&entity_organizations, None)
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    entities.insert(
        "locations".to_string(),
        Value::Array(
            dedupe_list(&entity_locations, None)
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );

    let mut readability = serde_json::Map::new();
    readability.insert(
        "method".to_string(),
        Value::String("Flesch-Kincaid".to_string()),
    );
    readability.insert("score".to_string(), value_from_f64(0.0));
    readability.insert("level".to_string(), Value::String("Unknown".to_string()));

    let mut out = serde_json::Map::new();
    out.insert("summary_250".to_string(), Value::String(s250_joined));
    out.insert("summary_1000".to_string(), Value::String(summary_1000));
    out.insert("tldr".to_string(), Value::String(tldr));
    out.insert(
        "key_ideas".to_string(),
        Value::Array(
            dedupe_list(&key_ideas, Some(10))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    out.insert(
        "topic_tags".to_string(),
        Value::Array(
            dedupe_list(&topic_tags, Some(8))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    out.insert("entities".to_string(), Value::Object(entities));
    out.insert(
        "estimated_reading_time_min".to_string(),
        Value::Number(Number::from(ert_sum.max(0))),
    );
    out.insert("key_stats".to_string(), Value::Array(key_stats));
    out.insert(
        "answered_questions".to_string(),
        Value::Array(
            dedupe_list(&answered, None)
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    out.insert("readability".to_string(), Value::Object(readability));
    out.insert(
        "seo_keywords".to_string(),
        Value::Array(
            dedupe_list(&seo_keywords, Some(15))
                .into_iter()
                .map(Value::String)
                .collect(),
        ),
    );
    out.insert("insights".to_string(), Value::Object(insights));
    Value::Object(out)
}

fn empty_summary_payload() -> Value {
    serde_json::json!({
        "summary_250": "",
        "summary_1000": "",
        "tldr": "",
        "key_ideas": [],
        "topic_tags": [],
        "entities": {
            "people": [],
            "organizations": [],
            "locations": [],
        },
        "estimated_reading_time_min": 0,
        "key_stats": [],
        "answered_questions": [],
        "readability": {
            "method": "Flesch-Kincaid",
            "score": 0.0,
            "level": "Unknown",
        },
        "seo_keywords": [],
        "insights": {
            "topic_overview": "",
            "new_facts": [],
            "open_questions": [],
            "suggested_sources": [],
            "expansion_topics": [],
            "next_exploration": [],
            "caution": null,
        },
    })
}

fn dedupe_list(items: &[String], limit: Option<usize>) -> Vec<String> {
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut out: Vec<String> = Vec::new();
    for item in items {
        let stripped = item.trim();
        if stripped.is_empty() {
            continue;
        }
        let key = stripped.to_lowercase();
        if !seen.contains(&key) {
            seen.insert(key);
            out.push(stripped.to_string());
            if let Some(max_len) = limit {
                if out.len() >= max_len {
                    break;
                }
            }
        }
    }
    out
}

fn extract_sentences(text: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut chars = text.trim().chars().peekable();

    while let Some(ch) = chars.next() {
        current.push(ch);
        if matches!(ch, '.' | '!' | '?') {
            let mut saw_ws = false;
            while let Some(next) = chars.peek().copied() {
                if next.is_whitespace() {
                    saw_ws = true;
                    current.push(next);
                    chars.next();
                } else {
                    break;
                }
            }
            if saw_ws {
                let candidate = current.trim();
                if candidate.chars().count() > 15 {
                    out.push(candidate.to_string());
                }
                current.clear();
            }
        }
    }

    let tail = current.trim();
    if !tail.is_empty() && tail.chars().count() > 15 {
        out.push(tail.to_string());
    }
    out
}

fn dedupe_sentences(parts: &[String]) -> String {
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut deduped: Vec<String> = Vec::new();
    for part in parts {
        for sentence in extract_sentences(part) {
            let key = sentence.trim().to_lowercase();
            if !seen.contains(&key) {
                seen.insert(key);
                deduped.push(sentence);
            }
        }
    }
    deduped.join(" ")
}

fn select_best_summary_250(parts: &[String]) -> String {
    let deduped = dedupe_list(parts, None);
    deduped
        .into_iter()
        .max_by_key(|item| item.chars().count())
        .unwrap_or_default()
}

fn merge_key_stats(current: &[Value], incoming: Option<&Value>, limit: usize) -> Vec<Value> {
    let incoming_items: &[Value] = match incoming {
        Some(Value::Array(items)) => items.as_slice(),
        _ => &[],
    };

    let mut out: Vec<Value> = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();

    for item in current.iter().chain(incoming_items.iter()) {
        let Some(item_obj) = item.as_object() else {
            continue;
        };
        let label = item_obj
            .get("label")
            .map(stringify_like_python)
            .unwrap_or_default()
            .trim()
            .to_string();
        if label.is_empty() {
            continue;
        }
        let key = label.to_lowercase();
        if seen.contains(&key) {
            continue;
        }
        seen.insert(key);

        let mut entry = serde_json::Map::new();
        entry.insert("label".to_string(), Value::String(label));
        entry.insert(
            "value".to_string(),
            value_from_f64(parse_python_float(item_obj.get("value"))),
        );
        entry.insert(
            "unit".to_string(),
            item_obj.get("unit").cloned().unwrap_or(Value::Null),
        );
        entry.insert(
            "source_excerpt".to_string(),
            item_obj
                .get("source_excerpt")
                .cloned()
                .unwrap_or(Value::Null),
        );
        out.push(Value::Object(entry));
        if out.len() >= limit {
            break;
        }
    }
    out
}

fn read_string_list(value: Option<&Value>, trim: bool) -> Vec<String> {
    match value {
        Some(Value::Array(items)) => items
            .iter()
            .map(|item| {
                let text = stringify_like_python(item);
                if trim {
                    text.trim().to_string()
                } else {
                    text
                }
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn pick_or_value<'a>(primary: Option<&'a Value>, fallback: Option<&'a Value>) -> Option<&'a Value> {
    if let Some(value) = primary {
        if python_truthy_value(value) {
            return Some(value);
        }
    }
    fallback
}

fn python_truthy_value(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(flag) => *flag,
        Value::Number(num) => {
            if let Some(i) = num.as_i64() {
                return i != 0;
            }
            if let Some(u) = num.as_u64() {
                return u != 0;
            }
            num.as_f64().is_some_and(|float| float != 0.0)
        }
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(obj) => !obj.is_empty(),
    }
}

fn stringify_like_python(value: &Value) -> String {
    match value {
        Value::Null => "None".to_string(),
        Value::Bool(true) => "True".to_string(),
        Value::Bool(false) => "False".to_string(),
        Value::String(text) => text.clone(),
        Value::Number(num) => num.to_string(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

fn parse_python_int(value: Option<&Value>) -> Option<i64> {
    match value {
        None | Some(Value::Null) => Some(0),
        Some(Value::Bool(flag)) => Some(i64::from(*flag)),
        Some(Value::Number(num)) => num
            .as_i64()
            .or_else(|| num.as_u64().map(|v| v as i64))
            .or_else(|| num.as_f64().map(|v| v as i64)),
        Some(Value::String(text)) => text.parse::<i64>().ok(),
        Some(Value::Array(_)) | Some(Value::Object(_)) => None,
    }
}

fn parse_python_float(value: Option<&Value>) -> f64 {
    match value {
        None | Some(Value::Null) => 0.0,
        Some(Value::Bool(flag)) => {
            if *flag {
                1.0
            } else {
                0.0
            }
        }
        Some(Value::Number(num)) => num.as_f64().unwrap_or(0.0),
        Some(Value::String(text)) => text.parse::<f64>().unwrap_or(0.0),
        Some(Value::Array(_)) | Some(Value::Object(_)) => 0.0,
    }
}

fn value_from_f64(value: f64) -> Value {
    if !value.is_finite() {
        return Value::Number(Number::from(0));
    }
    if let Some(number) = Number::from_f64(value) {
        Value::Number(number)
    } else {
        Value::Number(Number::from(0))
    }
}

fn python_json_dumps_value(value: &Value) -> String {
    match value {
        Value::Array(items) => {
            let rendered: Vec<String> = items
                .iter()
                .map(|item| serde_json::to_string(item).unwrap_or_else(|_| "null".to_string()))
                .collect();
            format!("[{}]", rendered.join(", "))
        }
        _ => serde_json::to_string(value).unwrap_or_else(|_| "null".to_string()),
    }
}

fn detect_summary_content_type_hint(content: &str) -> String {
    let lower: String = content
        .chars()
        .take(2000)
        .collect::<String>()
        .to_lowercase();
    if ["abstract", "methodology", "doi:", "et al.", "arxiv"]
        .iter()
        .any(|needle| lower.contains(needle))
    {
        return "CONTENT HINT: Research paper. Focus on methodology, findings, and limitations.\n"
            .to_string();
    }
    if [
        "step 1",
        "how to",
        "tutorial",
        "prerequisites",
        "getting started",
    ]
    .iter()
    .any(|needle| lower.contains(needle))
    {
        return "CONTENT HINT: Tutorial. Focus on steps, prerequisites, and outcomes.\n"
            .to_string();
    }
    if [
        "breaking:",
        "reuters",
        "reported today",
        "press release",
        "associated press",
    ]
    .iter()
    .any(|needle| lower.contains(needle))
    {
        return "CONTENT HINT: News article. Focus on who, what, when, where, why.\n".to_string();
    }
    if [
        "in my opinion",
        "i think",
        "i believe",
        "editorial",
        "commentary",
    ]
    .iter()
    .any(|needle| lower.contains(needle))
    {
        return "CONTENT HINT: Opinion piece. Focus on the author's thesis and supporting arguments.\n"
            .to_string();
    }
    String::new()
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
    fn chunk_sentence_plan_snapshot_groups_sentences() {
        let input = ChunkSentencePlanInput {
            content_text: "First sentence. Second sentence! Third sentence?".to_string(),
            lang: "en".to_string(),
            max_chars: 20,
        };

        let snapshot = build_chunk_sentence_plan_snapshot(&input);
        assert_eq!(snapshot.lang, "en");
        assert_eq!(snapshot.chunk_size, 20);
        assert_eq!(snapshot.sentences.len(), 3);
        assert_eq!(snapshot.chunk_count, snapshot.chunks.len());
        assert!(snapshot.chunk_count >= 2);
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

    #[test]
    fn content_cleaner_removes_noise_sections() {
        let input = ContentCleanerInput {
            content_text: "Intro line.\n\n### Related Articles\njunk item\njunk item\njunk item\n\n## Main\nBody text.\n\nComments\nFirst!\n".to_string(),
        };

        let snapshot = build_content_cleaner_snapshot(&input);
        assert!(snapshot.content_text.contains("Intro line."));
        assert!(snapshot.content_text.contains("## Main"));
        assert!(snapshot.content_text.contains("Body text."));
        assert!(!snapshot.content_text.contains("Related Articles"));
        assert!(!snapshot.content_text.contains("Comments"));
        assert!(!snapshot.content_text.contains("junk item"));
    }

    #[test]
    fn summary_aggregate_snapshot_merges_chunks() {
        let input = SummaryAggregateInput {
            summaries: vec![
                serde_json::json!({
                    "summary_250": "Chunk one summary is detailed enough.",
                    "summary_1000": "Chunk one. Shared sentence.",
                    "tldr": "Chunk one short.",
                    "key_ideas": ["A", "B"],
                    "topic_tags": ["rust"],
                    "entities": {"people": ["Ada"], "organizations": [], "locations": ["EU"]},
                    "estimated_reading_time_min": 3,
                    "answered_questions": ["Why now?"],
                    "seo_keywords": ["migration"],
                    "insights": {
                        "topic_overview": "Overview one.",
                        "new_facts": [{"fact": "Fact A", "why_it_matters": "Important", "source_hint": null, "confidence": 0.8}],
                        "open_questions": ["What changed?"],
                        "suggested_sources": ["Spec"],
                        "expansion_topics": ["Contracts"],
                        "next_exploration": ["Benchmarks"],
                        "caution": "Watch latency."
                    }
                }),
                serde_json::json!({
                    "summary_250": "Second chunk summary.",
                    "summary_1000": "Chunk two. Shared sentence.",
                    "tldr": "Chunk two short.",
                    "key_ideas": ["B", "C"],
                    "topic_tags": ["Rust", "performance"],
                    "entities": {"people": ["ada"], "organizations": ["BSR"], "locations": ["EU"]},
                    "estimated_reading_time_min": 2,
                    "answered_questions": ["What next?"],
                    "seo_keywords": ["migration", "rust"],
                    "insights": {
                        "topic_overview": "Overview two.",
                        "new_facts": [{"fact": "Fact B", "why_it_matters": "", "source_hint": "changelog", "confidence": 0.6}],
                        "open_questions": ["What changed?"],
                        "suggested_sources": ["Roadmap"],
                        "expansion_topics": ["Tooling"],
                        "next_exploration": ["Load tests"],
                        "caution": "Watch latency."
                    }
                }),
            ],
        };

        let snapshot = build_summary_aggregate_snapshot(&input);
        let object = snapshot
            .as_object()
            .expect("summary aggregate should be object");
        assert_eq!(
            object
                .get("estimated_reading_time_min")
                .and_then(Value::as_i64)
                .unwrap_or_default(),
            5
        );
        assert!(object
            .get("key_ideas")
            .and_then(Value::as_array)
            .is_some_and(|ideas| ideas.len() == 3));
        assert!(object
            .get("insights")
            .and_then(Value::as_object)
            .and_then(|insights| insights.get("new_facts"))
            .and_then(Value::as_array)
            .is_some_and(|facts| facts.len() == 2));
    }

    #[test]
    fn chunk_synthesis_prompt_snapshot_builds_prompt() {
        let input = ChunkSynthesisPromptInput {
            aggregated: serde_json::json!({
                "tldr": "TLDR section.",
                "summary_250": "Summary section.",
                "key_ideas": ["Idea A", "Idea B"],
            }),
            chosen_lang: "ru".to_string(),
        };

        let snapshot = build_chunk_synthesis_prompt_snapshot(&input);
        assert!(snapshot.context_text.contains("TLDR DRAFT:\nTLDR section."));
        assert!(snapshot
            .context_text
            .contains("DETAILED SUMMARY DRAFT:\nSummary section."));
        assert!(snapshot
            .context_text
            .contains("KEY IDEAS DRAFT:\n[\"Idea A\", \"Idea B\"]"));
        assert!(snapshot.user_content.contains("Respond in Russian."));
        assert!(snapshot.user_content.contains("DRAFT CONTENT START"));
        assert!(snapshot.user_content.contains("DRAFT CONTENT END"));
    }

    #[test]
    fn summary_user_content_snapshot_builds_user_prompt() {
        let input = SummaryUserContentInput {
            content_for_summary: "Breaking: Reuters reported today that migration completed."
                .to_string(),
            chosen_lang: "ru".to_string(),
            search_context: "WEB SEARCH CONTEXT:\n- source".to_string(),
        };

        let snapshot = build_summary_user_content_snapshot(&input);
        assert_eq!(
            snapshot.content_hint,
            "CONTENT HINT: News article. Focus on who, what, when, where, why.\n"
        );
        assert!(snapshot.user_content.contains("Respond in Russian."));
        assert!(snapshot.user_content.contains("CONTENT START"));
        assert!(snapshot.user_content.contains("CONTENT END"));
        assert!(snapshot.user_content.contains("WEB SEARCH CONTEXT"));
    }
}
