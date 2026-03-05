use std::collections::{BTreeMap, HashMap, HashSet};
use std::path::Path;

use rusqlite::{params_from_iter, types::Value as SqlValue, Connection};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Number, Value};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum SummaryValidationError {
    #[error("summary payload must be a non-empty object")]
    InvalidPayload,
    #[error("summary payload too large")]
    PayloadTooLarge,
}

#[derive(Debug, Error)]
pub enum SqliteCompatibilityError {
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
    #[error("sqlite schema is not compatible")]
    IncompatibleSchema,
    #[error("sqlite roundtrip validation failed")]
    RoundtripFailed,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SqliteCompatibilityReport {
    pub compatible: bool,
    pub missing_tables: Vec<String>,
    pub missing_columns: BTreeMap<String, Vec<String>>,
}

pub fn validate_and_shape_summary(payload: &Value) -> Result<Value, SummaryValidationError> {
    let obj = payload
        .as_object()
        .ok_or(SummaryValidationError::InvalidPayload)?;
    if obj.is_empty() {
        return Err(SummaryValidationError::InvalidPayload);
    }
    if payload.to_string().len() > 100_000 {
        return Err(SummaryValidationError::PayloadTooLarge);
    }

    let p = normalize_field_names(obj);

    // Summary field backfill.
    let mut summary_250 = get_trimmed_string(&p, "summary_250");
    let mut summary_1000 = get_trimmed_string(&p, "summary_1000");
    let mut tldr = get_trimmed_string(&p, "tldr");

    if summary_1000.is_empty() {
        let fallback = get_trimmed_string(&p, "summary");
        if !fallback.is_empty() {
            summary_1000 = fallback;
        }
    }

    if tldr.is_empty() && !summary_1000.is_empty() {
        tldr = summary_1000.clone();
    }
    if summary_1000.is_empty() && !tldr.is_empty() {
        summary_1000 = tldr.clone();
    }
    if summary_250.is_empty() && !summary_1000.is_empty() {
        summary_250 = cap_text(&summary_1000, 250);
    }
    if summary_250.is_empty() && !tldr.is_empty() {
        summary_250 = cap_text(&tldr, 250);
    }

    if summary_250.is_empty() && summary_1000.is_empty() && tldr.is_empty() {
        if let Some(fallback) = summary_fallback_from_supporting_fields(&p) {
            summary_1000 = cap_text(&fallback, 1000);
            summary_250 = cap_text(&summary_1000, 250);
            tldr = summary_1000.clone();
        }
    }

    summary_250 = cap_text(&summary_250, 250);
    summary_1000 = cap_text(&summary_1000, 1000);

    if summary_1000.is_empty() && !summary_250.is_empty() {
        summary_1000 = summary_250.clone();
    }
    if tldr.is_empty() {
        tldr = if !summary_1000.is_empty() {
            summary_1000.clone()
        } else {
            summary_250.clone()
        };
    }

    if tldr_needs_enrichment(&tldr, &summary_1000) {
        tldr = enrich_tldr_from_payload(
            if !summary_1000.is_empty() {
                &summary_1000
            } else {
                &tldr
            },
            &p,
        );
    }

    let key_ideas = string_list_keep_duplicates(p.get("key_ideas"));

    let topic_tags = hash_tagify(clean_string_list(p.get("topic_tags"), Some(10)), 10);

    let entities = normalize_entities_field(p.get("entities"));

    let estimated_reading_time_min = p
        .get("estimated_reading_time_min")
        .and_then(value_to_i64)
        .map(|v| v.max(0))
        .unwrap_or(0);

    let key_stats = shape_key_stats(p.get("key_stats"));

    let answered_questions = clean_string_list(p.get("answered_questions"), None);

    let read_src = if !tldr.is_empty() {
        tldr.clone()
    } else if !summary_1000.is_empty() {
        summary_1000.clone()
    } else {
        summary_250.clone()
    };

    let readability = shape_readability(p.get("readability"), &read_src);

    let mut seo_keywords = clean_string_list(p.get("seo_keywords"), None);
    let mut topic_tags_effective = topic_tags;
    if seo_keywords.is_empty() || topic_tags_effective.is_empty() {
        let terms = extract_keywords_simple(&read_src, 10);
        if seo_keywords.is_empty() {
            seo_keywords = terms.clone();
        }
        if topic_tags_effective.is_empty() && !terms.is_empty() {
            topic_tags_effective = hash_tagify(terms, 10);
        }
    }

    let metadata = shape_metadata(p.get("metadata"));
    let article_id = determine_article_id(&p, &metadata);

    let base_text = [summary_1000.clone(), summary_250.clone(), tldr.clone()]
        .join(" ")
        .trim()
        .to_string();
    let topics_clean: Vec<String> = topic_tags_effective
        .iter()
        .map(|tag| tag.trim_start_matches('#').to_string())
        .collect();

    let language = p
        .get("language")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(ToString::to_string);

    let query_expansion_keywords = shape_query_expansion_keywords(
        p.get("query_expansion_keywords"),
        &base_text,
        &topics_clean,
        &seo_keywords,
        &key_ideas,
    );
    let semantic_boosters =
        shape_semantic_boosters(p.get("semantic_boosters"), &base_text, 15, 320);
    let semantic_chunks = shape_semantic_chunks(
        p.get("semantic_chunks").or_else(|| p.get("chunks")),
        article_id.as_deref(),
        &topics_clean,
        language.as_deref(),
    );

    let source_type = normalize_source_type(p.get("source_type"));
    let temporal_freshness = normalize_temporal_freshness(p.get("temporal_freshness"));

    let extractive_quotes = shape_extractive_quotes(p.get("extractive_quotes"));
    let highlights = clean_string_list(p.get("highlights"), None);
    let questions_answered = shape_questions_answered(p.get("questions_answered"));
    let categories = clean_string_list(p.get("categories"), None);
    let topic_taxonomy = shape_topic_taxonomy(p.get("topic_taxonomy"));
    let hallucination_risk = normalize_hallucination_risk(p.get("hallucination_risk"));
    let confidence = clamp_confidence(p.get("confidence"));
    let forwarded_post_extras = shape_forwarded_post_extras(p.get("forwarded_post_extras"));
    let key_points_to_remember = clean_string_list(p.get("key_points_to_remember"), None);
    let insights = shape_insights(p.get("insights"));
    let quality = shape_quality(p.get("quality"));

    let mut out = Map::new();
    out.insert("summary_250".to_string(), Value::String(summary_250));
    out.insert("summary_1000".to_string(), Value::String(summary_1000));
    out.insert("tldr".to_string(), Value::String(tldr));
    out.insert("key_ideas".to_string(), strings_to_value(&key_ideas));
    out.insert(
        "topic_tags".to_string(),
        strings_to_value(&topic_tags_effective),
    );
    out.insert("entities".to_string(), entities);
    out.insert(
        "estimated_reading_time_min".to_string(),
        Value::Number(Number::from(estimated_reading_time_min)),
    );
    out.insert("key_stats".to_string(), Value::Array(key_stats));
    out.insert(
        "answered_questions".to_string(),
        strings_to_value(&answered_questions),
    );
    out.insert("readability".to_string(), readability);
    out.insert("seo_keywords".to_string(), strings_to_value(&seo_keywords));
    out.insert(
        "query_expansion_keywords".to_string(),
        strings_to_value(&query_expansion_keywords),
    );
    out.insert(
        "semantic_boosters".to_string(),
        strings_to_value(&semantic_boosters),
    );
    out.insert("semantic_chunks".to_string(), Value::Array(semantic_chunks));
    out.insert(
        "article_id".to_string(),
        article_id.map(Value::String).unwrap_or(Value::Null),
    );
    out.insert("source_type".to_string(), Value::String(source_type));
    out.insert(
        "temporal_freshness".to_string(),
        Value::String(temporal_freshness),
    );
    out.insert("metadata".to_string(), metadata);
    out.insert(
        "extractive_quotes".to_string(),
        Value::Array(extractive_quotes),
    );
    out.insert("highlights".to_string(), strings_to_value(&highlights));
    out.insert(
        "questions_answered".to_string(),
        Value::Array(questions_answered),
    );
    out.insert("categories".to_string(), strings_to_value(&categories));
    out.insert("topic_taxonomy".to_string(), Value::Array(topic_taxonomy));
    out.insert(
        "hallucination_risk".to_string(),
        Value::String(hallucination_risk),
    );
    out.insert(
        "confidence".to_string(),
        Value::Number(Number::from_f64(confidence).unwrap_or_else(|| Number::from(1))),
    );
    out.insert("forwarded_post_extras".to_string(), forwarded_post_extras);
    out.insert(
        "key_points_to_remember".to_string(),
        strings_to_value(&key_points_to_remember),
    );
    out.insert("insights".to_string(), insights);
    out.insert("quality".to_string(), quality);

    Ok(Value::Object(out))
}

pub fn check_sqlite_compatibility(
    db_path: impl AsRef<Path>,
) -> Result<SqliteCompatibilityReport, SqliteCompatibilityError> {
    let conn = Connection::open(db_path)?;
    check_sqlite_compatibility_conn(&conn)
}

pub fn sqlite_roundtrip_smoke(db_path: impl AsRef<Path>) -> Result<(), SqliteCompatibilityError> {
    let conn = Connection::open(db_path)?;
    let report = check_sqlite_compatibility_conn(&conn)?;
    if !report.compatible {
        return Err(SqliteCompatibilityError::IncompatibleSchema);
    }

    let tx = conn.unchecked_transaction()?;
    let request_columns = table_columns(&tx, "requests")?;
    let summary_columns = table_columns(&tx, "summaries")?;

    let now_ms = unix_now_millis();
    let mut request_insert_cols: Vec<&str> = Vec::new();
    let mut request_insert_terms: Vec<String> = Vec::new();
    let mut request_insert_values: Vec<SqlValue> = Vec::new();

    request_insert_cols.push("type");
    request_insert_terms.push("?".to_string());
    request_insert_values.push(SqlValue::Text("url".to_string()));
    request_insert_cols.push("status");
    request_insert_terms.push("?".to_string());
    request_insert_values.push(SqlValue::Text("pending".to_string()));
    if request_columns.contains("input_url") {
        request_insert_cols.push("input_url");
        request_insert_terms.push("?".to_string());
        request_insert_values.push(SqlValue::Text(
            "https://example.com/rust-m2-smoke".to_string(),
        ));
    }
    if request_columns.contains("normalized_url") {
        request_insert_cols.push("normalized_url");
        request_insert_terms.push("?".to_string());
        request_insert_values.push(SqlValue::Text(
            "https://example.com/rust-m2-smoke".to_string(),
        ));
    }
    if request_columns.contains("created_at") {
        request_insert_cols.push("created_at");
        request_insert_terms.push("CURRENT_TIMESTAMP".to_string());
    }
    if request_columns.contains("updated_at") {
        request_insert_cols.push("updated_at");
        request_insert_terms.push("CURRENT_TIMESTAMP".to_string());
    }
    if request_columns.contains("server_version") {
        request_insert_cols.push("server_version");
        request_insert_terms.push("?".to_string());
        request_insert_values.push(SqlValue::Integer(now_ms));
    }
    if request_columns.contains("is_deleted") {
        request_insert_cols.push("is_deleted");
        request_insert_terms.push("?".to_string());
        request_insert_values.push(SqlValue::Integer(0));
    }

    let request_sql = format!(
        "INSERT INTO requests ({}) VALUES ({})",
        request_insert_cols.join(", "),
        request_insert_terms.join(", ")
    );
    tx.execute(&request_sql, params_from_iter(request_insert_values))?;
    let request_id = tx.last_insert_rowid();

    let summary_payload = json!({
        "summary_250": "rust-m2-smoke",
        "summary_1000": "rust-m2-smoke",
        "tldr": "rust-m2-smoke"
    })
    .to_string();

    let mut summary_insert_cols: Vec<&str> = Vec::new();
    let mut summary_insert_terms: Vec<String> = Vec::new();
    let mut summary_insert_values: Vec<SqlValue> = Vec::new();

    summary_insert_cols.push("request_id");
    summary_insert_terms.push("?".to_string());
    summary_insert_values.push(SqlValue::Integer(request_id));
    if summary_columns.contains("lang") {
        summary_insert_cols.push("lang");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Text("en".to_string()));
    }
    summary_insert_cols.push("json_payload");
    summary_insert_terms.push("?".to_string());
    summary_insert_values.push(SqlValue::Text(summary_payload));
    if summary_columns.contains("insights_json") {
        summary_insert_cols.push("insights_json");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Text("{}".to_string()));
    }
    if summary_columns.contains("version") {
        summary_insert_cols.push("version");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Integer(1));
    }
    if summary_columns.contains("server_version") {
        summary_insert_cols.push("server_version");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Integer(now_ms));
    }
    if summary_columns.contains("is_read") {
        summary_insert_cols.push("is_read");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Integer(0));
    }
    if summary_columns.contains("is_favorited") {
        summary_insert_cols.push("is_favorited");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Integer(0));
    }
    if summary_columns.contains("is_deleted") {
        summary_insert_cols.push("is_deleted");
        summary_insert_terms.push("?".to_string());
        summary_insert_values.push(SqlValue::Integer(0));
    }
    if summary_columns.contains("updated_at") {
        summary_insert_cols.push("updated_at");
        summary_insert_terms.push("CURRENT_TIMESTAMP".to_string());
    }
    if summary_columns.contains("created_at") {
        summary_insert_cols.push("created_at");
        summary_insert_terms.push("CURRENT_TIMESTAMP".to_string());
    }

    let summary_sql = format!(
        "INSERT INTO summaries ({}) VALUES ({})",
        summary_insert_cols.join(", "),
        summary_insert_terms.join(", ")
    );
    tx.execute(&summary_sql, params_from_iter(summary_insert_values))?;

    let stored_payload: String = tx.query_row(
        "SELECT json_payload FROM summaries WHERE request_id = ?1",
        [request_id],
        |row| row.get(0),
    )?;

    let parsed_payload: Value = serde_json::from_str(&stored_payload)?;
    let summary_250 = parsed_payload
        .get("summary_250")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if summary_250 != "rust-m2-smoke" {
        return Err(SqliteCompatibilityError::RoundtripFailed);
    }

    tx.rollback()?;
    Ok(())
}

fn normalize_field_names(payload: &Map<String, Value>) -> Map<String, Value> {
    payload
        .iter()
        .map(|(key, value)| (map_field_name(key).to_string(), value.clone()))
        .collect()
}

fn map_field_name(field: &str) -> &str {
    match field {
        "summary" => "summary_1000",
        "summary250" => "summary_250",
        "summary1000" => "summary_1000",
        "keyideas" | "keyIdeas" => "key_ideas",
        "topictags" | "topicTags" => "topic_tags",
        "estimatedreadingtimemin" | "estimatedReadingTimeMin" => "estimated_reading_time_min",
        "keystats" | "keyStats" => "key_stats",
        "answeredquestions" | "answeredQuestions" => "answered_questions",
        "seokeywords" | "seoKeywords" => "seo_keywords",
        "extractivequotes" | "extractiveQuotes" => "extractive_quotes",
        "questionsanswered" | "questionsAnswered" => "questions_answered",
        "topictaxonomy" | "topicTaxonomy" => "topic_taxonomy",
        "hallucinationrisk" | "hallucinationRisk" => "hallucination_risk",
        "forwardedpostextras" | "forwardedPostExtras" => "forwarded_post_extras",
        "keypointstoremember" | "keyPointsToRemember" => "key_points_to_remember",
        _ => field,
    }
}

fn strings_to_value(values: &[String]) -> Value {
    Value::Array(
        values
            .iter()
            .map(|value| Value::String(value.clone()))
            .collect(),
    )
}

fn get_trimmed_string(map: &Map<String, Value>, key: &str) -> String {
    map.get(key)
        .map(value_to_string)
        .unwrap_or_default()
        .trim()
        .to_string()
}

fn value_to_string(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::String(text) => text.clone(),
        Value::Bool(flag) => flag.to_string(),
        Value::Number(number) => number.to_string(),
        other => other.to_string(),
    }
}

fn value_to_i64(value: &Value) -> Option<i64> {
    match value {
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_f64().map(|v| v as i64)),
        Value::String(text) => text.trim().parse::<i64>().ok(),
        _ => None,
    }
}

fn value_to_f64(value: &Value) -> Option<f64> {
    match value {
        Value::Number(number) => number.as_f64(),
        Value::String(text) => text.trim().parse::<f64>().ok(),
        _ => None,
    }
}

fn clean_string_list(raw: Option<&Value>, limit: Option<usize>) -> Vec<String> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    let values: Vec<Value> = match raw {
        Some(Value::Array(items)) => items.clone(),
        Some(value) => vec![value.clone()],
        None => Vec::new(),
    };

    for item in values {
        let text = value_to_string(&item).trim().to_string();
        if text.is_empty() {
            continue;
        }
        let lowered = text.to_lowercase();
        if seen.contains(&lowered) {
            continue;
        }
        seen.insert(lowered);
        out.push(text);
        if let Some(max) = limit {
            if out.len() >= max {
                break;
            }
        }
    }

    out
}

fn string_list_keep_duplicates(raw: Option<&Value>) -> Vec<String> {
    let values: Vec<Value> = match raw {
        Some(Value::Array(items)) => items.clone(),
        Some(value) => vec![value.clone()],
        None => Vec::new(),
    };

    values
        .into_iter()
        .map(|item| value_to_string(&item).trim().to_string())
        .filter(|text| !text.is_empty())
        .collect()
}

fn dedupe_case_insensitive(values: Vec<String>) -> Vec<String> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    for value in values {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            continue;
        }
        let lowered = trimmed.to_lowercase();
        if lowered.len() > 500 {
            continue;
        }
        if lowered.contains('<')
            || lowered.contains('>')
            || lowered.contains("script")
            || lowered.contains("javascript")
        {
            continue;
        }
        if seen.insert(lowered) {
            out.push(trimmed.to_string());
        }
    }

    out
}

fn hash_tagify(tags: Vec<String>, max_tags: usize) -> Vec<String> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    let effective_limit = if max_tags == 0 || max_tags > 100 {
        10
    } else {
        max_tags
    };

    for mut tag in tags {
        tag = tag.trim().to_string();
        if tag.is_empty() || tag.len() > 100 {
            continue;
        }
        let lowered = tag.to_lowercase();
        if lowered.contains('<')
            || lowered.contains('>')
            || lowered.contains("script")
            || lowered.contains("javascript")
        {
            continue;
        }
        if !tag.starts_with('#') {
            tag = format!("#{tag}");
        }
        let key = tag.to_lowercase();
        if seen.insert(key) {
            out.push(tag);
        }
        if out.len() >= effective_limit {
            break;
        }
    }

    out
}

fn cap_text(text: &str, limit: usize) -> String {
    if text.chars().count() <= limit {
        return text.to_string();
    }

    let snippet: String = text.chars().take(limit).collect();
    for sep in [". ", "! ", "? ", "; ", ", "] {
        if let Some(idx) = snippet.rfind(sep) {
            if idx > 0 {
                return snippet[..idx + sep.len()].trim().to_string();
            }
        }
    }

    snippet.trim().to_string()
}

fn normalize_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn simple_similarity_ratio(a: &str, b: &str) -> f64 {
    if a.is_empty() || b.is_empty() {
        return 0.0;
    }

    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();

    let mut matches = 0usize;
    for ch in &a_chars {
        if b_chars.contains(ch) {
            matches += 1;
        }
    }

    let max_len = a_chars.len().max(b_chars.len()) as f64;
    (matches as f64 / max_len).min(1.0)
}

fn tldr_needs_enrichment(tldr: &str, summary_1000: &str) -> bool {
    let tldr_norm = normalize_whitespace(tldr);
    let summary_norm = normalize_whitespace(summary_1000);

    if tldr_norm.is_empty() || summary_norm.is_empty() {
        return false;
    }
    if tldr_norm == summary_norm {
        return true;
    }

    let similarity = simple_similarity_ratio(&tldr_norm, &summary_norm);
    if similarity >= 0.92 {
        return true;
    }

    if (summary_norm.starts_with(&tldr_norm) || tldr_norm.starts_with(&summary_norm))
        && (tldr_norm.len() as isize - summary_norm.len() as isize).abs() <= 120
    {
        return true;
    }

    tldr_norm.len() <= summary_norm.len() + 40
}

fn summary_fallback_from_supporting_fields(payload: &Map<String, Value>) -> Option<String> {
    let mut snippets = Vec::new();
    let mut seen = HashSet::new();

    let mut add_snippet = |snippet: String| {
        if snippets.len() >= 8 {
            return;
        }
        let trimmed = snippet.trim().to_string();
        if trimmed.is_empty() {
            return;
        }
        let key = trimmed.to_lowercase();
        if seen.insert(key) {
            snippets.push(trimmed);
        }
    };

    for key in ["topic_overview", "overview"] {
        let text = get_trimmed_string(payload, key);
        if !text.is_empty() {
            add_snippet(text);
        }
    }

    for key in [
        "summary_paragraphs",
        "summary_bullets",
        "highlights",
        "key_points_to_remember",
        "key_ideas",
        "answered_questions",
    ] {
        match payload.get(key) {
            Some(Value::Array(items)) => {
                for item in items {
                    add_snippet(value_to_string(item));
                }
            }
            Some(value) => add_snippet(value_to_string(value)),
            None => {}
        }
    }

    if let Some(Value::Array(items)) = payload.get("questions_answered") {
        for item in items {
            if let Value::Object(obj) = item {
                let question = obj.get("question").map(value_to_string).unwrap_or_default();
                let answer = obj.get("answer").map(value_to_string).unwrap_or_default();
                if !question.trim().is_empty() && !answer.trim().is_empty() {
                    add_snippet(format!("{}: {}", question.trim(), answer.trim()));
                } else if !question.trim().is_empty() {
                    add_snippet(question);
                } else if !answer.trim().is_empty() {
                    add_snippet(answer);
                }
            } else {
                add_snippet(value_to_string(item));
            }
        }
    }

    if let Some(Value::Array(items)) = payload.get("extractive_quotes") {
        for item in items {
            if let Value::Object(obj) = item {
                let text = obj.get("text").map(value_to_string).unwrap_or_default();
                add_snippet(text);
            } else {
                add_snippet(value_to_string(item));
            }
        }
    }

    if let Some(Value::Object(insights)) = payload.get("insights") {
        for key in ["topic_overview", "caution"] {
            let text = insights.get(key).map(value_to_string).unwrap_or_default();
            add_snippet(text);
        }

        if let Some(Value::Array(new_facts)) = insights.get("new_facts") {
            for fact in new_facts {
                if let Value::Object(obj) = fact {
                    let fact_text = obj.get("fact").map(value_to_string).unwrap_or_default();
                    let why = obj
                        .get("why_it_matters")
                        .map(value_to_string)
                        .unwrap_or_default();
                    if !fact_text.trim().is_empty() && !why.trim().is_empty() {
                        add_snippet(format!("{} -- {}", fact_text.trim(), why.trim()));
                    } else {
                        add_snippet(if !fact_text.trim().is_empty() {
                            fact_text
                        } else {
                            why
                        });
                    }
                }
            }
        }
    }

    if snippets.is_empty() {
        return None;
    }

    Some(snippets.into_iter().take(6).collect::<Vec<_>>().join(" "))
}

fn enrich_tldr_from_payload(base_text: &str, payload: &Map<String, Value>) -> String {
    let mut segments = Vec::new();
    let mut seen = HashSet::new();

    let mut add_segment = |segment: String| {
        let trimmed = segment.trim().to_string();
        if trimmed.is_empty() {
            return;
        }
        let normalized = normalize_whitespace(&trimmed).to_lowercase();
        if seen.insert(normalized) {
            segments.push(trimmed);
        }
    };

    add_segment(base_text.to_string());

    let key_ideas = clean_string_list(payload.get("key_ideas"), Some(6));
    if !key_ideas.is_empty() {
        add_segment(format!("Key ideas: {}.", key_ideas.join("; ")));
    }

    let highlights = clean_string_list(payload.get("highlights"), Some(5));
    if !highlights.is_empty() {
        add_segment(format!("Highlights: {}.", highlights.join("; ")));
    }

    let mut stats_parts = Vec::new();
    if let Some(Value::Array(stats)) = payload.get("key_stats") {
        for stat in stats {
            if let Value::Object(obj) = stat {
                let label = obj.get("label").map(value_to_string).unwrap_or_default();
                let value = obj.get("value").and_then(value_to_f64);
                if label.trim().is_empty() || value.is_none() {
                    continue;
                }
                let unit = obj.get("unit").map(value_to_string).unwrap_or_default();
                let unit_part = if unit.trim().is_empty() {
                    String::new()
                } else {
                    format!(" {}", unit.trim())
                };
                stats_parts.push(format!("{}: {}{}", label.trim(), value.unwrap(), unit_part));
            }
        }
    }
    if !stats_parts.is_empty() {
        add_segment(format!("Key stats: {}.", stats_parts.join("; ")));
    }

    if let Some(Value::Array(items)) = payload.get("answered_questions") {
        let mut questions = Vec::new();
        for item in items {
            if let Value::Object(obj) = item {
                let question = obj.get("question").map(value_to_string).unwrap_or_default();
                let answer = obj.get("answer").map(value_to_string).unwrap_or_default();
                if !question.trim().is_empty() && !answer.trim().is_empty() {
                    questions.push(format!("{} -- {}", question.trim(), answer.trim()));
                } else if !question.trim().is_empty() {
                    questions.push(question.trim().to_string());
                }
            } else {
                let text = value_to_string(item);
                if !text.trim().is_empty() {
                    questions.push(text.trim().to_string());
                }
            }
        }
        let deduped = dedupe_case_insensitive(questions);
        if !deduped.is_empty() {
            add_segment(format!("Questions answered: {}.", deduped.join("; ")));
        }
    }

    if let Some(Value::Object(insights)) = payload.get("insights") {
        let topic_overview = insights
            .get("topic_overview")
            .map(value_to_string)
            .unwrap_or_default();
        if !topic_overview.trim().is_empty() {
            add_segment(topic_overview);
        }

        let caution = insights
            .get("caution")
            .map(value_to_string)
            .unwrap_or_default();
        if !caution.trim().is_empty() {
            add_segment(format!("Caution: {}", caution.trim()));
        }
    }

    if let Some(fallback) = summary_fallback_from_supporting_fields(payload) {
        add_segment(fallback);
    }

    let merged = segments.join(" ");
    if merged.trim().is_empty() {
        base_text.to_string()
    } else {
        cap_text(&merged, 2000)
    }
}

fn shape_key_stats(raw: Option<&Value>) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(Value::Array(items)) = raw else {
        return out;
    };

    for item in items {
        let Value::Object(obj) = item else {
            continue;
        };

        let label = obj.get("label").map(value_to_string).unwrap_or_default();
        let Some(value) = obj.get("value").and_then(value_to_f64) else {
            continue;
        };
        if label.trim().is_empty() {
            continue;
        }

        let unit = obj.get("unit").map(value_to_string).unwrap_or_default();
        let source_excerpt = obj
            .get("source_excerpt")
            .map(value_to_string)
            .unwrap_or_default();

        out.push(json!({
            "label": label.trim(),
            "value": value,
            "unit": if unit.trim().is_empty() { Value::Null } else { Value::String(unit.trim().to_string()) },
            "source_excerpt": if source_excerpt.trim().is_empty() {
                Value::Null
            } else {
                Value::String(source_excerpt.trim().to_string())
            }
        }));
    }

    out
}

fn shape_readability(raw: Option<&Value>, read_src: &str) -> Value {
    let mut method = "Flesch-Kincaid".to_string();
    let mut score = 0.0;
    let mut level = String::new();

    if let Some(Value::Object(obj)) = raw {
        let maybe_method = obj.get("method").map(value_to_string).unwrap_or_default();
        if !maybe_method.trim().is_empty() {
            method = maybe_method.trim().to_string();
        }

        if let Some(raw_score) = obj.get("score").and_then(value_to_f64) {
            if raw_score != 0.0 {
                score = raw_score;
            }
        }

        let maybe_level = obj.get("level").map(value_to_string).unwrap_or_default();
        if !maybe_level.trim().is_empty() {
            level = maybe_level.trim().to_string();
        }
    }

    if score == 0.0 {
        score = compute_flesch_reading_ease(read_src);
        method = "Flesch-Kincaid".to_string();
    }

    if level.is_empty() {
        level = readability_level_for_score(score);
    }

    json!({
        "method": method,
        "score": score,
        "level": level,
    })
}

fn readability_level_for_score(score: f64) -> String {
    if score >= 90.0 {
        "Very Easy".to_string()
    } else if score >= 80.0 {
        "Easy".to_string()
    } else if score >= 70.0 {
        "Fairly Easy".to_string()
    } else if score >= 60.0 {
        "Standard".to_string()
    } else if score >= 50.0 {
        "Fairly Difficult".to_string()
    } else if score >= 30.0 {
        "Difficult".to_string()
    } else {
        "Very Confusing".to_string()
    }
}

fn compute_flesch_reading_ease(text: &str) -> f64 {
    if text.trim().is_empty() {
        return 0.0;
    }

    let sentences: Vec<&str> = text
        .split(['.', '!', '?'])
        .map(str::trim)
        .filter(|segment| !segment.is_empty())
        .collect();
    let sentence_count = sentences.len().max(1) as f64;

    let words = extract_word_tokens(text);
    let word_count = words.len().max(1) as f64;

    let syllable_count: usize = words.iter().map(|word| count_syllables(word)).sum();
    let syllables = syllable_count.max(1) as f64;

    let score = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (syllables / word_count);
    score.clamp(0.0, 100.0)
}

fn extract_word_tokens(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut buffer = String::new();

    for ch in text.chars() {
        if ch.is_alphanumeric() || ch == '_' {
            buffer.push(ch.to_ascii_lowercase());
        } else if !buffer.is_empty() {
            tokens.push(buffer.clone());
            buffer.clear();
        }
    }

    if !buffer.is_empty() {
        tokens.push(buffer);
    }

    tokens
}

fn count_syllables(word: &str) -> usize {
    if word.is_empty() {
        return 1;
    }

    let vowels = ['a', 'e', 'i', 'o', 'u', 'y'];
    let chars: Vec<char> = word.chars().collect();
    let mut count = 0usize;
    let mut prev_is_vowel = false;

    for ch in &chars {
        let is_vowel = vowels.contains(ch);
        if is_vowel && !prev_is_vowel {
            count += 1;
        }
        prev_is_vowel = is_vowel;
    }

    if word.ends_with('e') && count > 1 {
        count -= 1;
    }

    count.max(1)
}

fn extract_keywords_simple(text: &str, topn: usize) -> Vec<String> {
    if text.trim().is_empty() {
        return Vec::new();
    }

    let stop_words: HashSet<&'static str> = [
        "this", "that", "with", "from", "have", "they", "what", "been", "will", "would", "there",
        "their", "about", "which", "when", "make", "like", "time", "just", "know", "take", "into",
        "year", "some", "could", "them", "other", "than", "then", "look", "only", "come", "over",
        "also", "back", "after", "work", "first", "well", "even", "want", "because", "these",
        "give", "most", "very",
    ]
    .into_iter()
    .collect();

    let mut counts: HashMap<String, usize> = HashMap::new();
    let mut order: Vec<String> = Vec::new();

    for token in extract_word_tokens(text) {
        if token.len() < 4 || stop_words.contains(token.as_str()) {
            continue;
        }
        let counter = counts.entry(token.clone()).or_insert(0);
        *counter += 1;
        if *counter == 1 {
            order.push(token);
        }
    }

    order.sort_by(|a, b| {
        let count_a = counts.get(a).copied().unwrap_or_default();
        let count_b = counts.get(b).copied().unwrap_or_default();
        count_b.cmp(&count_a).then_with(|| a.cmp(b))
    });

    order.into_iter().take(topn).collect()
}

fn shape_query_expansion_keywords(
    raw: Option<&Value>,
    base_text: &str,
    topic_tags: &[String],
    seo_keywords: &[String],
    key_ideas: &[String],
) -> Vec<String> {
    let mut seeds = clean_string_list(raw, None);
    for topic in topic_tags {
        seeds.push(topic.trim_start_matches('#').to_string());
    }
    seeds.extend(seo_keywords.iter().cloned());
    seeds.extend(key_ideas.iter().cloned());
    seeds.extend(extract_keywords_simple(base_text, 40));

    let mut deduped = dedupe_case_insensitive(seeds);
    if deduped.len() > 30 {
        deduped.truncate(30);
    }
    deduped
}

fn shape_semantic_boosters(
    raw: Option<&Value>,
    base_text: &str,
    max_items: usize,
    max_length: usize,
) -> Vec<String> {
    let mut boosters: Vec<String> = clean_string_list(raw, None)
        .into_iter()
        .map(|value| cap_text(&value, max_length))
        .collect();

    let sentences: Vec<String> = base_text
        .split(['.', '!', '?'])
        .map(str::trim)
        .filter(|sentence| !sentence.is_empty() && sentence.len() > 20)
        .map(ToString::to_string)
        .collect();

    for sentence in sentences {
        if boosters.len() >= max_items {
            break;
        }
        let capped = cap_text(&sentence, max_length);
        if !boosters.contains(&capped) {
            boosters.push(capped);
        }
    }

    if boosters.len() > max_items {
        boosters.truncate(max_items);
    }

    boosters
}

fn shape_metadata(raw: Option<&Value>) -> Value {
    let obj = raw.and_then(Value::as_object);
    let field = |key: &str| {
        obj.and_then(|map| map.get(key))
            .map(value_to_string)
            .unwrap_or_default()
            .trim()
            .to_string()
    };

    json!({
        "title": nullable_string(field("title")),
        "canonical_url": nullable_string(field("canonical_url")),
        "domain": nullable_string(field("domain")),
        "author": nullable_string(field("author")),
        "published_at": nullable_string(field("published_at")),
        "last_updated": nullable_string(field("last_updated")),
    })
}

fn nullable_string(text: String) -> Value {
    if text.trim().is_empty() {
        Value::Null
    } else {
        Value::String(text)
    }
}

fn determine_article_id(payload: &Map<String, Value>, metadata: &Value) -> Option<String> {
    if let Some(article_id) = payload.get("article_id").map(value_to_string) {
        if !article_id.trim().is_empty() {
            return Some(article_id.trim().to_string());
        }
    }

    let meta = metadata.as_object();
    for key in ["canonical_url", "url"] {
        if let Some(candidate) = meta
            .and_then(|obj| obj.get(key))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            return Some(candidate.to_string());
        }
    }

    None
}

fn shape_extractive_quotes(raw: Option<&Value>) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(Value::Array(items)) = raw else {
        return out;
    };

    for item in items {
        let Value::Object(obj) = item else {
            continue;
        };

        let text = obj.get("text").map(value_to_string).unwrap_or_default();
        if text.trim().is_empty() {
            continue;
        }
        let span = obj
            .get("source_span")
            .map(value_to_string)
            .unwrap_or_default();

        out.push(json!({
            "text": text.trim(),
            "source_span": if span.trim().is_empty() { Value::Null } else { Value::String(span.trim().to_string()) }
        }));
    }

    out
}

fn shape_questions_answered(raw: Option<&Value>) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(Value::Array(items)) = raw else {
        return out;
    };

    for item in items {
        match item {
            Value::Object(obj) => {
                let question = obj.get("question").map(value_to_string).unwrap_or_default();
                let answer = obj.get("answer").map(value_to_string).unwrap_or_default();
                if !question.trim().is_empty() && !answer.trim().is_empty() {
                    out.push(json!({"question": question.trim(), "answer": answer.trim()}));
                }
            }
            Value::String(text) => {
                let trimmed = text.trim();
                if trimmed.is_empty() {
                    continue;
                }

                if let Some((question, answer)) = parse_qa_string(trimmed) {
                    out.push(json!({"question": question, "answer": answer}));
                } else {
                    out.push(json!({"question": trimmed, "answer": ""}));
                }
            }
            _ => {}
        }
    }

    out
}

fn parse_qa_string(raw: &str) -> Option<(String, String)> {
    let lowercase = raw.to_lowercase();

    if lowercase.starts_with("q:") {
        if let Some(answer_idx) = lowercase.find("a:") {
            let question = raw[2..answer_idx].trim();
            let answer = raw[answer_idx + 2..].trim();
            if !question.is_empty() && !answer.is_empty() {
                return Some((question.to_string(), answer.to_string()));
            }
        }
    }

    if lowercase.starts_with("question:") {
        if let Some(answer_idx) = lowercase.find("answer:") {
            let question = raw[9..answer_idx].trim();
            let answer = raw[answer_idx + 7..].trim();
            if !question.is_empty() && !answer.is_empty() {
                return Some((question.to_string(), answer.to_string()));
            }
        }
    }

    if let Some(question_mark_idx) = raw.find('?') {
        let question = raw[..question_mark_idx].trim();
        let answer = raw[question_mark_idx + 1..].trim();
        if !question.is_empty() && !answer.is_empty() {
            return Some((question.to_string(), answer.to_string()));
        }
    }

    None
}

fn shape_topic_taxonomy(raw: Option<&Value>) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(Value::Array(items)) = raw else {
        return out;
    };

    for item in items {
        let Value::Object(obj) = item else {
            continue;
        };

        let label = obj.get("label").map(value_to_string).unwrap_or_default();
        if label.trim().is_empty() {
            continue;
        }

        let score = obj.get("score").and_then(value_to_f64).unwrap_or(0.0);
        let path = obj.get("path").map(value_to_string).unwrap_or_default();

        out.push(json!({
            "label": label.trim(),
            "score": score,
            "path": if path.trim().is_empty() { Value::Null } else { Value::String(path.trim().to_string()) }
        }));
    }

    out
}

fn normalize_hallucination_risk(raw: Option<&Value>) -> String {
    let value = raw
        .map(value_to_string)
        .unwrap_or_else(|| "low".to_string());
    let normalized = value.trim().to_lowercase();
    if ["low", "med", "high"].contains(&normalized.as_str()) {
        normalized
    } else {
        "low".to_string()
    }
}

fn clamp_confidence(raw: Option<&Value>) -> f64 {
    let value = raw.and_then(value_to_f64).unwrap_or(1.0);
    value.clamp(0.0, 1.0)
}

fn normalize_source_type(raw: Option<&Value>) -> String {
    let value = raw
        .map(value_to_string)
        .unwrap_or_else(|| "blog".to_string());
    let normalized = value.trim().to_lowercase();
    if [
        "news",
        "blog",
        "research",
        "opinion",
        "tutorial",
        "reference",
    ]
    .contains(&normalized.as_str())
    {
        normalized
    } else {
        "blog".to_string()
    }
}

fn normalize_temporal_freshness(raw: Option<&Value>) -> String {
    let value = raw
        .map(value_to_string)
        .unwrap_or_else(|| "evergreen".to_string());
    let normalized = value.trim().to_lowercase();
    if ["breaking", "recent", "evergreen"].contains(&normalized.as_str()) {
        normalized
    } else {
        "evergreen".to_string()
    }
}

fn shape_forwarded_post_extras(raw: Option<&Value>) -> Value {
    let Some(Value::Object(obj)) = raw else {
        return Value::Null;
    };

    json!({
        "channel_id": obj.get("channel_id").and_then(value_to_i64),
        "channel_title": nullable_string(obj.get("channel_title").map(value_to_string).unwrap_or_default()),
        "channel_username": nullable_string(obj.get("channel_username").map(value_to_string).unwrap_or_default()),
        "message_id": obj.get("message_id").and_then(value_to_i64),
        "post_datetime": nullable_string(obj.get("post_datetime").map(value_to_string).unwrap_or_default()),
        "hashtags": string_list_keep_duplicates(obj.get("hashtags")),
        "mentions": string_list_keep_duplicates(obj.get("mentions")),
    })
}

fn shape_insights(raw: Option<&Value>) -> Value {
    let Some(Value::Object(obj)) = raw else {
        return json!({
            "topic_overview": "",
            "new_facts": [],
            "open_questions": [],
            "suggested_sources": [],
            "expansion_topics": [],
            "next_exploration": [],
            "caution": Value::Null,
            "critique": [],
        });
    };

    let mut new_facts = Vec::new();
    let mut seen_facts = HashSet::new();
    if let Some(Value::Array(items)) = obj.get("new_facts") {
        for item in items {
            let Value::Object(fact) = item else {
                continue;
            };

            let fact_text = fact.get("fact").map(value_to_string).unwrap_or_default();
            if fact_text.trim().is_empty() {
                continue;
            }
            let key = fact_text.trim().to_lowercase();
            if !seen_facts.insert(key) {
                continue;
            }

            let why = fact
                .get("why_it_matters")
                .map(value_to_string)
                .unwrap_or_default();
            let source_hint = fact
                .get("source_hint")
                .map(value_to_string)
                .unwrap_or_default();
            let confidence = match fact.get("confidence") {
                Some(Value::Number(number)) => {
                    if let Some(value) = number.as_f64() {
                        Value::Number(Number::from_f64(value).unwrap_or_else(|| Number::from(0)))
                    } else {
                        Value::Null
                    }
                }
                Some(Value::String(text)) if !text.trim().is_empty() => {
                    Value::String(text.trim().to_string())
                }
                _ => Value::Null,
            };

            new_facts.push(json!({
                "fact": fact_text.trim(),
                "why_it_matters": if why.trim().is_empty() { Value::Null } else { Value::String(why.trim().to_string()) },
                "source_hint": if source_hint.trim().is_empty() { Value::Null } else { Value::String(source_hint.trim().to_string()) },
                "confidence": confidence,
            }));
        }
    }

    let caution = obj.get("caution").map(value_to_string).unwrap_or_default();

    json!({
        "topic_overview": obj.get("topic_overview").map(value_to_string).unwrap_or_default().trim(),
        "new_facts": new_facts,
        "open_questions": clean_string_list(obj.get("open_questions"), None),
        "suggested_sources": clean_string_list(obj.get("suggested_sources"), None),
        "expansion_topics": clean_string_list(obj.get("expansion_topics"), None),
        "next_exploration": clean_string_list(obj.get("next_exploration"), None),
        "caution": if caution.trim().is_empty() { Value::Null } else { Value::String(caution.trim().to_string()) },
        "critique": clean_string_list(obj.get("critique"), None),
    })
}

fn shape_quality(raw: Option<&Value>) -> Value {
    let Some(Value::Object(obj)) = raw else {
        return json!({
            "author_bias": Value::Null,
            "emotional_tone": Value::Null,
            "missing_perspectives": [],
            "evidence_quality": Value::Null,
        });
    };

    let author_bias = obj
        .get("author_bias")
        .map(value_to_string)
        .unwrap_or_default();
    let emotional_tone = obj
        .get("emotional_tone")
        .map(value_to_string)
        .unwrap_or_default();
    let evidence_quality = obj
        .get("evidence_quality")
        .map(value_to_string)
        .unwrap_or_default();

    json!({
        "author_bias": if author_bias.trim().is_empty() { Value::Null } else { Value::String(author_bias.trim().to_string()) },
        "emotional_tone": if emotional_tone.trim().is_empty() { Value::Null } else { Value::String(emotional_tone.trim().to_string()) },
        "missing_perspectives": clean_string_list(obj.get("missing_perspectives"), None),
        "evidence_quality": if evidence_quality.trim().is_empty() { Value::Null } else { Value::String(evidence_quality.trim().to_string()) },
    })
}

fn shape_semantic_chunks(
    raw: Option<&Value>,
    article_id: Option<&str>,
    topics: &[String],
    language: Option<&str>,
) -> Vec<Value> {
    let mut out = Vec::new();
    let Some(Value::Array(items)) = raw else {
        return out;
    };

    for item in items {
        let Value::Object(obj) = item else {
            continue;
        };

        let text = obj
            .get("text")
            .or_else(|| obj.get("content"))
            .map(value_to_string)
            .unwrap_or_default();
        if text.trim().is_empty() {
            continue;
        }

        let local_summary = obj
            .get("local_summary")
            .or_else(|| obj.get("summary"))
            .map(value_to_string)
            .unwrap_or_default();
        let local_summary_shaped = if local_summary.trim().is_empty() {
            String::new()
        } else {
            cap_text(local_summary.trim(), 480)
        };
        let local_keywords = clean_string_list(obj.get("local_keywords"), Some(8));

        let article_id_value = obj
            .get("article_id")
            .map(value_to_string)
            .or_else(|| article_id.map(ToString::to_string))
            .unwrap_or_default();
        let language_value = obj
            .get("language")
            .map(value_to_string)
            .or_else(|| language.map(ToString::to_string))
            .unwrap_or_default();

        let raw_topics = obj.get("topics");
        let chunk_topics = if raw_topics.is_some() {
            clean_string_list(raw_topics, None)
        } else {
            dedupe_case_insensitive(topics.to_vec())
        };

        out.push(json!({
            "text": text.trim(),
            "local_summary": local_summary_shaped,
            "local_keywords": local_keywords,
            "article_id": if article_id_value.trim().is_empty() { Value::Null } else { Value::String(article_id_value.trim().to_string()) },
            "section": obj.get("section").cloned().unwrap_or(Value::Null),
            "language": if language_value.trim().is_empty() { Value::Null } else { Value::String(language_value.trim().to_string()) },
            "topics": chunk_topics,
        }));
    }

    out
}

fn normalize_entities_field(raw: Option<&Value>) -> Value {
    let mut buckets: HashMap<&'static str, Vec<String>> = HashMap::from([
        ("people", Vec::new()),
        ("organizations", Vec::new()),
        ("locations", Vec::new()),
    ]);

    match raw {
        Some(Value::Object(obj)) => {
            for (key, value) in obj {
                if let Some(bucket) = resolve_entity_bucket(key) {
                    buckets
                        .entry(bucket)
                        .or_default()
                        .extend(coerce_entity_values(value));
                }
            }
        }
        Some(Value::Array(items)) => {
            for item in items {
                if let Value::Object(obj) = item {
                    let bucket = obj
                        .get("type")
                        .and_then(Value::as_str)
                        .and_then(resolve_entity_bucket)
                        .or_else(|| {
                            obj.get("category")
                                .and_then(Value::as_str)
                                .and_then(resolve_entity_bucket)
                        })
                        .or_else(|| {
                            obj.get("label")
                                .and_then(Value::as_str)
                                .and_then(resolve_entity_bucket)
                        })
                        .or_else(|| {
                            obj.get("group")
                                .and_then(Value::as_str)
                                .and_then(resolve_entity_bucket)
                        })
                        .unwrap_or("people");
                    buckets
                        .entry(bucket)
                        .or_default()
                        .extend(coerce_entity_values(item));
                } else {
                    buckets
                        .entry("people")
                        .or_default()
                        .extend(coerce_entity_values(item));
                }
            }
        }
        Some(value) => {
            buckets
                .entry("people")
                .or_default()
                .extend(coerce_entity_values(value));
        }
        None => {}
    }

    json!({
        "people": dedupe_case_insensitive(buckets.remove("people").unwrap_or_default()),
        "organizations": dedupe_case_insensitive(buckets.remove("organizations").unwrap_or_default()),
        "locations": dedupe_case_insensitive(buckets.remove("locations").unwrap_or_default()),
    })
}

fn resolve_entity_bucket(raw: &str) -> Option<&'static str> {
    match raw.trim().to_lowercase().as_str() {
        "person" | "persons" | "individual" | "individuals" | "people" => Some("people"),
        "organization" | "organizations" | "org" | "orgs" | "company" | "companies"
        | "institution" | "institutions" => Some("organizations"),
        "location" | "locations" | "place" | "places" | "country" | "countries" | "city"
        | "cities" => Some("locations"),
        _ => None,
    }
}

fn coerce_entity_values(raw: &Value) -> Vec<String> {
    match raw {
        Value::Null => Vec::new(),
        Value::String(text) => {
            let trimmed = text.trim();
            if trimmed.is_empty() {
                Vec::new()
            } else {
                vec![trimmed.to_string()]
            }
        }
        Value::Bool(flag) => vec![flag.to_string()],
        Value::Number(number) => vec![number.to_string()],
        Value::Array(items) => items.iter().flat_map(coerce_entity_values).collect(),
        Value::Object(obj) => {
            let preferred_keys = ["entities", "items", "names", "values", "list", "members"];
            for key in preferred_keys {
                if let Some(value) = obj.get(key) {
                    return coerce_entity_values(value);
                }
            }

            let fallback_keys = ["name", "label", "entity", "text", "value"];
            for key in fallback_keys {
                if let Some(value) = obj.get(key) {
                    return coerce_entity_values(value);
                }
            }

            obj.values().flat_map(coerce_entity_values).collect()
        }
    }
}

const SQLITE_REQUIRED_COLUMNS: &[(&str, &[&str])] = &[
    ("requests", &["id", "type", "status"]),
    ("summaries", &["id", "request_id", "json_payload"]),
];
const SQLITE_ROUNDTRIP_REQUEST_INSERT_COLUMNS: &[&str] = &[
    "type",
    "status",
    "input_url",
    "normalized_url",
    "created_at",
    "updated_at",
    "server_version",
    "is_deleted",
];
const SQLITE_ROUNDTRIP_SUMMARY_INSERT_COLUMNS: &[&str] = &[
    "request_id",
    "lang",
    "json_payload",
    "insights_json",
    "version",
    "server_version",
    "is_read",
    "is_favorited",
    "is_deleted",
    "updated_at",
    "created_at",
];

fn check_sqlite_compatibility_conn(
    conn: &Connection,
) -> Result<SqliteCompatibilityReport, SqliteCompatibilityError> {
    let mut missing_tables = Vec::new();
    let mut missing_columns: BTreeMap<String, Vec<String>> = BTreeMap::new();

    for (table_name, required_columns) in SQLITE_REQUIRED_COLUMNS {
        if !table_exists(conn, table_name)? {
            missing_tables.push((*table_name).to_string());
            continue;
        }

        let existing_columns = table_columns(conn, table_name)?;
        let mut missing_for_table: Vec<String> = required_columns
            .iter()
            .filter(|column| !existing_columns.contains(**column))
            .map(|column| (*column).to_string())
            .collect();

        if let Some(insert_columns) = roundtrip_insert_columns(table_name) {
            let unsupported_required_columns =
                required_insert_columns_without_defaults(conn, table_name)?
                    .into_iter()
                    .filter(|column| !insert_columns.contains(&column.as_str()))
                    .map(|column| {
                        format!("{column} (required insert column unsupported by roundtrip)")
                    });
            missing_for_table.extend(unsupported_required_columns);
        }

        missing_for_table.sort();

        if !missing_for_table.is_empty() {
            missing_columns.insert((*table_name).to_string(), missing_for_table);
        }
    }

    Ok(SqliteCompatibilityReport {
        compatible: missing_tables.is_empty() && missing_columns.is_empty(),
        missing_tables,
        missing_columns,
    })
}

fn table_exists(conn: &Connection, table_name: &str) -> Result<bool, rusqlite::Error> {
    let exists: i64 = conn.query_row(
        "SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name=?1",
        [table_name],
        |row| row.get(0),
    )?;
    Ok(exists > 0)
}

fn table_columns(conn: &Connection, table_name: &str) -> Result<HashSet<String>, rusqlite::Error> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table_name})"))?;
    let rows = stmt.query_map([], |row| row.get::<_, String>(1))?;

    let mut columns = HashSet::new();
    for column in rows {
        columns.insert(column?);
    }

    Ok(columns)
}

fn roundtrip_insert_columns(table_name: &str) -> Option<&'static [&'static str]> {
    match table_name {
        "requests" => Some(SQLITE_ROUNDTRIP_REQUEST_INSERT_COLUMNS),
        "summaries" => Some(SQLITE_ROUNDTRIP_SUMMARY_INSERT_COLUMNS),
        _ => None,
    }
}

fn required_insert_columns_without_defaults(
    conn: &Connection,
    table_name: &str,
) -> Result<Vec<String>, rusqlite::Error> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({table_name})"))?;
    let rows = stmt.query_map([], |row| {
        let name: String = row.get(1)?;
        let not_null: i64 = row.get(3)?;
        let default_value: Option<String> = row.get(4)?;
        let part_of_pk: i64 = row.get(5)?;
        Ok((name, not_null != 0, default_value.is_some(), part_of_pk != 0))
    })?;

    let mut required = Vec::new();
    for row in rows {
        let (name, not_null, has_default, part_of_pk) = row?;
        if not_null && !has_default && !part_of_pk {
            required.push(name);
        }
    }

    Ok(required)
}

fn unix_now_millis() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};

    let now = SystemTime::now();
    let duration = now
        .duration_since(UNIX_EPOCH)
        .unwrap_or_else(|_| std::time::Duration::from_millis(0));
    duration.as_millis() as i64
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::NamedTempFile;

    #[test]
    fn caps_and_backfills_summary_fields() {
        let input = json!({
            "summary250": "A ".repeat(160),
            "summary1000": "B ".repeat(700),
            "tldr": "",
        });

        let output = validate_and_shape_summary(&input).expect("should shape summary");

        let summary_250 = output
            .get("summary_250")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let summary_1000 = output
            .get("summary_1000")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let tldr = output
            .get("tldr")
            .and_then(Value::as_str)
            .unwrap_or_default();

        assert!(summary_250.chars().count() <= 250);
        assert!(summary_1000.chars().count() <= 1000);
        assert!(!tldr.is_empty());
    }

    #[test]
    fn normalizes_tags_and_entities() {
        let input = json!({
            "summary_250": "short",
            "summary_1000": "long",
            "tldr": "long enough to avoid enrichment mismatch x x x x x x x x",
            "topicTags": ["Tech", "tech", "rust"],
            "entities": {
                "people": ["Alice", "alice"],
                "organization": ["OpenAI", "openai"]
            }
        });

        let output = validate_and_shape_summary(&input).expect("should shape summary");

        assert_eq!(
            output.get("topic_tags").cloned().unwrap_or(Value::Null),
            json!(["#Tech", "#rust"])
        );

        assert_eq!(
            output
                .get("entities")
                .and_then(Value::as_object)
                .and_then(|obj| obj.get("people"))
                .cloned()
                .unwrap_or(Value::Null),
            json!(["Alice"])
        );
        assert_eq!(
            output
                .get("entities")
                .and_then(Value::as_object)
                .and_then(|obj| obj.get("organizations"))
                .cloned()
                .unwrap_or(Value::Null),
            json!(["OpenAI"])
        );
    }

    #[test]
    fn sqlite_compatibility_report_detects_missing_schema() {
        let file = NamedTempFile::new().expect("temp file");
        let conn = Connection::open(file.path()).expect("open sqlite");

        conn.execute_batch(
            "
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY,
                type TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                server_version INTEGER,
                is_deleted INTEGER
            );
            ",
        )
        .expect("create partial requests table");

        let report = check_sqlite_compatibility_conn(&conn).expect("check report");
        assert!(!report.compatible);
        assert!(report.missing_tables.contains(&"summaries".to_string()));
    }

    #[test]
    fn sqlite_roundtrip_smoke_works_with_minimum_schema() {
        let file = NamedTempFile::new().expect("temp file");
        let conn = Connection::open(file.path()).expect("open sqlite");

        conn.execute_batch(
            "
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                correlation_id TEXT,
                user_id INTEGER,
                input_url TEXT,
                normalized_url TEXT,
                dedupe_hash TEXT,
                content_text TEXT,
                created_at TEXT,
                updated_at TEXT,
                server_version INTEGER,
                is_deleted INTEGER DEFAULT 0
            );

            CREATE TABLE summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER UNIQUE,
                lang TEXT,
                json_payload TEXT,
                insights_json TEXT,
                version INTEGER,
                server_version INTEGER,
                is_read INTEGER DEFAULT 0,
                is_favorited INTEGER DEFAULT 0,
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT,
                updated_at TEXT,
                created_at TEXT,
                FOREIGN KEY(request_id) REFERENCES requests(id)
            );
            ",
        )
        .expect("create schema");

        drop(conn);
        sqlite_roundtrip_smoke(file.path()).expect("roundtrip should work");
    }

    #[test]
    fn sqlite_roundtrip_uses_sql_timestamp_expressions() {
        let file = NamedTempFile::new().expect("temp file");
        let conn = Connection::open(file.path()).expect("open sqlite");

        conn.execute_batch(
            "
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL CHECK(created_at != 'CURRENT_TIMESTAMP'),
                updated_at TEXT NOT NULL CHECK(updated_at != 'CURRENT_TIMESTAMP')
            );

            CREATE TABLE summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER UNIQUE,
                json_payload TEXT NOT NULL,
                created_at TEXT NOT NULL CHECK(created_at != 'CURRENT_TIMESTAMP'),
                updated_at TEXT NOT NULL CHECK(updated_at != 'CURRENT_TIMESTAMP'),
                FOREIGN KEY(request_id) REFERENCES requests(id)
            );
            ",
        )
        .expect("create schema with timestamp checks");

        drop(conn);
        sqlite_roundtrip_smoke(file.path()).expect("roundtrip should use SQL timestamps");
    }

    #[test]
    fn sqlite_compatibility_detects_required_columns_unsupported_by_roundtrip() {
        let file = NamedTempFile::new().expect("temp file");
        let conn = Connection::open(file.path()).expect("open sqlite");

        conn.execute_batch(
            "
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                must_fill TEXT NOT NULL
            );

            CREATE TABLE summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER UNIQUE,
                json_payload TEXT NOT NULL
            );
            ",
        )
        .expect("create schema with extra required column");

        let report = check_sqlite_compatibility_conn(&conn).expect("check report");
        assert!(!report.compatible);
        assert!(report.missing_columns.get("requests").is_some_and(|columns| {
            columns.iter().any(|column| {
                column.contains("must_fill")
                    && column.contains("required insert column unsupported by roundtrip")
            })
        }));
    }
}
