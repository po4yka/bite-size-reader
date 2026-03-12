use rusqlite::types::Value as SqlValue;
use rusqlite::{params, params_from_iter, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{get_user_by_telegram_id, PersistenceError};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ApiSummaryRecord {
    pub id: i64,
    pub request_id: i64,
    pub lang: Option<String>,
    pub json_payload: Option<Value>,
    pub insights_json: Option<Value>,
    pub version: i64,
    pub is_read: bool,
    pub is_favorited: bool,
    pub is_deleted: bool,
    pub deleted_at: Option<String>,
    pub updated_at: Option<String>,
    pub created_at: Option<String>,
    pub request_type: Option<String>,
    pub request_status: Option<String>,
    pub request_correlation_id: Option<String>,
    pub request_input_url: Option<String>,
    pub request_normalized_url: Option<String>,
    pub request_dedupe_hash: Option<String>,
    pub request_lang_detected: Option<String>,
    pub request_content_text: Option<String>,
    pub request_created_at: Option<String>,
    pub request_updated_at: Option<String>,
    pub user_id: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ApiRequestRecord {
    pub id: i64,
    pub request_type: String,
    pub status: String,
    pub correlation_id: Option<String>,
    pub user_id: Option<i64>,
    pub chat_id: Option<i64>,
    pub input_url: Option<String>,
    pub normalized_url: Option<String>,
    pub dedupe_hash: Option<String>,
    pub input_message_id: Option<i64>,
    pub fwd_from_chat_id: Option<i64>,
    pub fwd_from_msg_id: Option<i64>,
    pub lang_detected: Option<String>,
    pub content_text: Option<String>,
    pub route_version: i64,
    pub error_type: Option<String>,
    pub error_message: Option<String>,
    pub processing_time_ms: Option<i64>,
    pub error_context_json: Option<Value>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ApiCrawlResultRecord {
    pub id: i64,
    pub request_id: i64,
    pub source_url: Option<String>,
    pub endpoint: Option<String>,
    pub http_status: Option<i64>,
    pub status: Option<String>,
    pub options_json: Option<Value>,
    pub correlation_id: Option<String>,
    pub content_markdown: Option<String>,
    pub content_html: Option<String>,
    pub structured_json: Option<Value>,
    pub metadata_json: Option<Value>,
    pub links_json: Option<Value>,
    pub firecrawl_success: Option<bool>,
    pub firecrawl_error_code: Option<String>,
    pub firecrawl_error_message: Option<String>,
    pub firecrawl_details_json: Option<Value>,
    pub raw_response_json: Option<Value>,
    pub latency_ms: Option<i64>,
    pub error_text: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ApiLlmCallRecord {
    pub id: i64,
    pub request_id: i64,
    pub provider: Option<String>,
    pub model: Option<String>,
    pub endpoint: Option<String>,
    pub tokens_prompt: Option<i64>,
    pub tokens_completion: Option<i64>,
    pub cost_usd: Option<f64>,
    pub latency_ms: Option<i64>,
    pub status: Option<String>,
    pub error_text: Option<String>,
    pub error_context_json: Option<Value>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AudioGenerationRecord {
    pub id: i64,
    pub summary_id: i64,
    pub provider: String,
    pub voice_id: String,
    pub model: String,
    pub file_path: Option<String>,
    pub file_size_bytes: Option<i64>,
    pub duration_sec: Option<f64>,
    pub char_count: Option<i64>,
    pub source_field: String,
    pub language: Option<String>,
    pub status: String,
    pub error_text: Option<String>,
    pub latency_ms: Option<i64>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UserDeviceRecord {
    pub id: i64,
    pub user_id: i64,
    pub token: String,
    pub platform: String,
    pub device_id: Option<String>,
    pub is_active: bool,
    pub last_seen_at: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SummaryListFilters<'a> {
    pub user_id: i64,
    pub limit: i64,
    pub offset: i64,
    pub is_read: Option<bool>,
    pub is_favorited: Option<bool>,
    pub lang: Option<&'a str>,
    pub start_date: Option<&'a str>,
    pub end_date: Option<&'a str>,
    pub sort: &'a str,
}

pub fn list_user_summaries(
    connection: &Connection,
    filters: &SummaryListFilters<'_>,
) -> Result<(Vec<ApiSummaryRecord>, i64, i64), PersistenceError> {
    let mut clauses = vec![
        "requests.user_id = ?".to_string(),
        "summaries.is_deleted = 0".to_string(),
    ];
    let mut values = vec![SqlValue::Integer(filters.user_id)];

    if let Some(is_read) = filters.is_read {
        clauses.push("summaries.is_read = ?".to_string());
        values.push(SqlValue::Integer(bool_to_int(is_read)));
    }
    if let Some(is_favorited) = filters.is_favorited {
        clauses.push("summaries.is_favorited = ?".to_string());
        values.push(SqlValue::Integer(bool_to_int(is_favorited)));
    }
    if let Some(lang) = normalize_optional_text(filters.lang) {
        clauses.push("summaries.lang = ?".to_string());
        values.push(SqlValue::Text(lang.to_string()));
    }
    if let Some(start_date) = normalize_optional_text(filters.start_date) {
        clauses.push("summaries.created_at >= ?".to_string());
        values.push(SqlValue::Text(start_date.to_string()));
    }
    if let Some(end_date) = normalize_optional_text(filters.end_date) {
        clauses.push("summaries.created_at <= ?".to_string());
        values.push(SqlValue::Text(end_date.to_string()));
    }

    let where_sql = clauses.join(" AND ");
    let order_sql = if filters.sort == "created_at_asc" {
        "requests.created_at ASC"
    } else {
        "requests.created_at DESC"
    };

    let mut list_values = values.clone();
    list_values.push(SqlValue::Integer(filters.limit.max(0)));
    list_values.push(SqlValue::Integer(filters.offset.max(0)));

    let list_sql = format!(
        r#"
        SELECT summaries.id, summaries.request_id, summaries.lang, summaries.json_payload,
               summaries.insights_json, summaries.version, summaries.is_read,
               summaries.is_favorited, summaries.is_deleted, summaries.deleted_at,
               summaries.updated_at, summaries.created_at, requests.type, requests.status,
               requests.correlation_id, requests.input_url, requests.normalized_url,
               requests.dedupe_hash, requests.lang_detected, requests.content_text,
               requests.created_at, requests.updated_at, requests.user_id
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
        "#
    );

    let mut list_statement = connection.prepare(&list_sql)?;
    let rows = list_statement.query_map(params_from_iter(list_values.iter()), map_summary_row)?;
    let mut summaries = Vec::new();
    for row in rows {
        summaries.push(row?);
    }

    let count_sql = format!(
        r#"
        SELECT COUNT(*)
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE {where_sql}
        "#
    );
    let total = connection.query_row(&count_sql, params_from_iter(values.iter()), |row| {
        row.get::<_, i64>(0)
    })?;

    let unread_count = connection.query_row(
        r#"
        SELECT COUNT(*)
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE requests.user_id = ?1
          AND summaries.is_read = 0
          AND summaries.is_deleted = 0
        "#,
        [filters.user_id],
        |row| row.get::<_, i64>(0),
    )?;

    Ok((summaries, total, unread_count))
}

pub fn get_summary_by_id_for_user(
    connection: &Connection,
    user_id: i64,
    summary_id: i64,
) -> Result<Option<ApiSummaryRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT summaries.id, summaries.request_id, summaries.lang, summaries.json_payload,
               summaries.insights_json, summaries.version, summaries.is_read,
               summaries.is_favorited, summaries.is_deleted, summaries.deleted_at,
               summaries.updated_at, summaries.created_at, requests.type, requests.status,
               requests.correlation_id, requests.input_url, requests.normalized_url,
               requests.dedupe_hash, requests.lang_detected, requests.content_text,
               requests.created_at, requests.updated_at, requests.user_id
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE summaries.id = ?1
          AND requests.user_id = ?2
          AND summaries.is_deleted = 0
        "#,
    )?;
    statement
        .query_row(params![summary_id, user_id], map_summary_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_summary_by_request_id(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<ApiSummaryRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT summaries.id, summaries.request_id, summaries.lang, summaries.json_payload,
               summaries.insights_json, summaries.version, summaries.is_read,
               summaries.is_favorited, summaries.is_deleted, summaries.deleted_at,
               summaries.updated_at, summaries.created_at, requests.type, requests.status,
               requests.correlation_id, requests.input_url, requests.normalized_url,
               requests.dedupe_hash, requests.lang_detected, requests.content_text,
               requests.created_at, requests.updated_at, requests.user_id
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE summaries.request_id = ?1
        "#,
    )?;
    statement
        .query_row([request_id], map_summary_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_summary_id_by_url_for_user(
    connection: &Connection,
    user_id: i64,
    url: &str,
) -> Result<Option<i64>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT summaries.id
        FROM requests
        JOIN summaries ON summaries.request_id = requests.id
        WHERE requests.user_id = ?1
          AND (requests.input_url = ?2 OR requests.normalized_url = ?2)
        ORDER BY requests.created_at DESC
        LIMIT 1
        "#,
    )?;
    statement
        .query_row(params![user_id, url], |row| row.get::<_, i64>(0))
        .optional()
        .map_err(PersistenceError::from)
}

pub fn mark_summary_as_read(
    connection: &Connection,
    summary_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE summaries
        SET is_read = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?1
        "#,
        [summary_id],
    )?;
    Ok(())
}

pub fn mark_summary_as_unread(
    connection: &Connection,
    summary_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE summaries
        SET is_read = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?1
        "#,
        [summary_id],
    )?;
    Ok(())
}

pub fn soft_delete_summary(
    connection: &Connection,
    summary_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE summaries
        SET is_deleted = 1,
            deleted_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?1
        "#,
        [summary_id],
    )?;
    Ok(())
}

pub fn toggle_summary_favorite(
    connection: &Connection,
    summary_id: i64,
) -> Result<bool, PersistenceError> {
    let current = connection
        .query_row(
            "SELECT is_favorited FROM summaries WHERE id = ?1",
            [summary_id],
            |row| row.get::<_, bool>(0),
        )
        .optional()?
        .ok_or_else(|| PersistenceError::MissingRow("summary favorite toggle".to_string()))?;
    let next = !current;
    connection.execute(
        r#"
        UPDATE summaries
        SET is_favorited = ?2,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?1
        "#,
        params![summary_id, bool_to_int(next)],
    )?;
    Ok(next)
}

pub fn get_request_by_id_for_user(
    connection: &Connection,
    user_id: i64,
    request_id: i64,
) -> Result<Option<ApiRequestRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, type, status, correlation_id, user_id, chat_id, input_url, normalized_url,
               dedupe_hash, input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected,
               content_text, route_version, error_type, error_message, processing_time_ms,
               error_context_json, created_at, updated_at
        FROM requests
        WHERE id = ?1 AND user_id = ?2
        "#,
    )?;
    statement
        .query_row(params![request_id, user_id], map_request_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn count_pending_requests_before(
    connection: &Connection,
    created_at: &str,
) -> Result<i64, PersistenceError> {
    connection
        .query_row(
            r#"
            SELECT COUNT(*)
            FROM requests
            WHERE status = 'pending' AND created_at < ?1
            "#,
            [created_at],
            |row| row.get::<_, i64>(0),
        )
        .map_err(PersistenceError::from)
}

pub fn list_llm_calls_by_request(
    connection: &Connection,
    request_id: i64,
) -> Result<Vec<ApiLlmCallRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, provider, model, endpoint, tokens_prompt, tokens_completion,
               cost_usd, latency_ms, status, error_text, error_context_json, created_at, updated_at
        FROM llm_calls
        WHERE request_id = ?1
        ORDER BY id ASC
        "#,
    )?;
    let rows = statement.query_map([request_id], map_llm_call_row)?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn get_latest_llm_call_by_request(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<ApiLlmCallRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, provider, model, endpoint, tokens_prompt, tokens_completion,
               cost_usd, latency_ms, status, error_text, error_context_json, created_at, updated_at
        FROM llm_calls
        WHERE request_id = ?1
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        "#,
    )?;
    statement
        .query_row([request_id], map_llm_call_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_crawl_result_by_request_api(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<ApiCrawlResultRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, source_url, endpoint, http_status, status, options_json,
               correlation_id, content_markdown, content_html, structured_json, metadata_json,
               links_json, firecrawl_success, firecrawl_error_code, firecrawl_error_message,
               firecrawl_details_json, raw_response_json, latency_ms, error_text, updated_at
        FROM crawl_results
        WHERE request_id = ?1
        "#,
    )?;
    statement
        .query_row([request_id], map_crawl_result_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn upsert_user_device(
    connection: &Connection,
    user_id: i64,
    token: &str,
    platform: &str,
    device_id: Option<&str>,
) -> Result<UserDeviceRecord, PersistenceError> {
    if get_user_by_telegram_id(connection, user_id)?.is_none() {
        return Err(PersistenceError::MissingRow("user device user".to_string()));
    }

    let existing = connection
        .query_row(
            r#"
            SELECT id, user_id, token, platform, device_id, is_active, last_seen_at, created_at
            FROM user_devices
            WHERE token = ?1
            "#,
            [token],
            map_user_device_row,
        )
        .optional()?;

    match existing {
        Some(_record) => {
            connection.execute(
                r#"
                UPDATE user_devices
                SET user_id = ?2,
                    platform = ?3,
                    device_id = ?4,
                    is_active = 1,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE token = ?1
                "#,
                params![token, user_id, platform, device_id],
            )?;
        }
        None => {
            connection.execute(
                r#"
                INSERT INTO user_devices (
                    user_id, token, platform, device_id, is_active, last_seen_at, created_at
                ) VALUES (?1, ?2, ?3, ?4, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                "#,
                params![user_id, token, platform, device_id],
            )?;
        }
    }

    connection
        .query_row(
            r#"
            SELECT id, user_id, token, platform, device_id, is_active, last_seen_at, created_at
            FROM user_devices
            WHERE token = ?1
            "#,
            [token],
            map_user_device_row,
        )
        .map_err(PersistenceError::from)
}

pub fn get_audio_generation_by_summary(
    connection: &Connection,
    summary_id: i64,
) -> Result<Option<AudioGenerationRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, summary_id, provider, voice_id, model, file_path, file_size_bytes,
               duration_sec, char_count, source_field, language, status, error_text,
               latency_ms, created_at
        FROM audio_generations
        WHERE summary_id = ?1
        LIMIT 1
        "#,
    )?;
    statement
        .query_row([summary_id], map_audio_generation_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn start_audio_generation(
    connection: &Connection,
    summary_id: i64,
    provider: &str,
    voice_id: &str,
    model: &str,
    source_field: &str,
    language: Option<&str>,
    char_count: i64,
) -> Result<AudioGenerationRecord, PersistenceError> {
    let existing = get_audio_generation_by_summary(connection, summary_id)?;
    match existing {
        Some(_) => {
            connection.execute(
                r#"
                UPDATE audio_generations
                SET provider = ?2,
                    voice_id = ?3,
                    model = ?4,
                    source_field = ?5,
                    language = ?6,
                    char_count = ?7,
                    status = 'generating',
                    error_text = NULL,
                    file_path = NULL,
                    file_size_bytes = NULL,
                    latency_ms = NULL
                WHERE summary_id = ?1
                "#,
                params![
                    summary_id,
                    provider,
                    voice_id,
                    model,
                    source_field,
                    language,
                    char_count
                ],
            )?;
        }
        None => {
            connection.execute(
                r#"
                INSERT INTO audio_generations (
                    summary_id, provider, voice_id, model, file_path, file_size_bytes,
                    duration_sec, char_count, source_field, language, status, error_text,
                    latency_ms, created_at
                ) VALUES (?1, ?2, ?3, ?4, NULL, NULL, NULL, ?5, ?6, ?7, 'generating', NULL, NULL, CURRENT_TIMESTAMP)
                "#,
                params![summary_id, provider, voice_id, model, char_count, source_field, language],
            )?;
        }
    }
    get_audio_generation_by_summary(connection, summary_id)?
        .ok_or_else(|| PersistenceError::MissingRow("audio generation".to_string()))
}

pub fn complete_audio_generation(
    connection: &Connection,
    summary_id: i64,
    file_path: &str,
    file_size_bytes: i64,
    latency_ms: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE audio_generations
        SET status = 'completed',
            file_path = ?2,
            file_size_bytes = ?3,
            latency_ms = ?4,
            error_text = NULL
        WHERE summary_id = ?1
        "#,
        params![summary_id, file_path, file_size_bytes, latency_ms],
    )?;
    Ok(())
}

pub fn fail_audio_generation(
    connection: &Connection,
    summary_id: i64,
    error_text: &str,
    latency_ms: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE audio_generations
        SET status = 'error',
            error_text = ?2,
            latency_ms = ?3
        WHERE summary_id = ?1
        "#,
        params![summary_id, error_text, latency_ms],
    )?;
    Ok(())
}

fn map_summary_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ApiSummaryRecord> {
    Ok(ApiSummaryRecord {
        id: row.get(0)?,
        request_id: row.get(1)?,
        lang: row.get(2)?,
        json_payload: parse_json_opt(row.get::<_, Option<String>>(3)?).map_err(to_sql_err)?,
        insights_json: parse_json_opt(row.get::<_, Option<String>>(4)?).map_err(to_sql_err)?,
        version: row.get(5)?,
        is_read: row.get(6)?,
        is_favorited: row.get(7)?,
        is_deleted: row.get(8)?,
        deleted_at: row.get(9)?,
        updated_at: row.get(10)?,
        created_at: row.get(11)?,
        request_type: row.get(12)?,
        request_status: row.get(13)?,
        request_correlation_id: row.get(14)?,
        request_input_url: row.get(15)?,
        request_normalized_url: row.get(16)?,
        request_dedupe_hash: row.get(17)?,
        request_lang_detected: row.get(18)?,
        request_content_text: row.get(19)?,
        request_created_at: row.get(20)?,
        request_updated_at: row.get(21)?,
        user_id: row.get(22)?,
    })
}

fn map_request_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ApiRequestRecord> {
    Ok(ApiRequestRecord {
        id: row.get(0)?,
        request_type: row.get(1)?,
        status: row.get(2)?,
        correlation_id: row.get(3)?,
        user_id: row.get(4)?,
        chat_id: row.get(5)?,
        input_url: row.get(6)?,
        normalized_url: row.get(7)?,
        dedupe_hash: row.get(8)?,
        input_message_id: row.get(9)?,
        fwd_from_chat_id: row.get(10)?,
        fwd_from_msg_id: row.get(11)?,
        lang_detected: row.get(12)?,
        content_text: row.get(13)?,
        route_version: row.get(14)?,
        error_type: row.get(15)?,
        error_message: row.get(16)?,
        processing_time_ms: row.get(17)?,
        error_context_json: parse_json_opt(row.get::<_, Option<String>>(18)?)
            .map_err(to_sql_err)?,
        created_at: row.get(19)?,
        updated_at: row.get(20)?,
    })
}

fn map_crawl_result_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ApiCrawlResultRecord> {
    Ok(ApiCrawlResultRecord {
        id: row.get(0)?,
        request_id: row.get(1)?,
        source_url: row.get(2)?,
        endpoint: row.get(3)?,
        http_status: row.get(4)?,
        status: row.get(5)?,
        options_json: parse_json_opt(row.get::<_, Option<String>>(6)?).map_err(to_sql_err)?,
        correlation_id: row.get(7)?,
        content_markdown: row.get(8)?,
        content_html: row.get(9)?,
        structured_json: parse_json_opt(row.get::<_, Option<String>>(10)?).map_err(to_sql_err)?,
        metadata_json: parse_json_opt(row.get::<_, Option<String>>(11)?).map_err(to_sql_err)?,
        links_json: parse_json_opt(row.get::<_, Option<String>>(12)?).map_err(to_sql_err)?,
        firecrawl_success: row.get(13)?,
        firecrawl_error_code: row.get(14)?,
        firecrawl_error_message: row.get(15)?,
        firecrawl_details_json: parse_json_opt(row.get::<_, Option<String>>(16)?)
            .map_err(to_sql_err)?,
        raw_response_json: parse_json_opt(row.get::<_, Option<String>>(17)?).map_err(to_sql_err)?,
        latency_ms: row.get(18)?,
        error_text: row.get(19)?,
        updated_at: row.get(20)?,
    })
}

fn map_llm_call_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ApiLlmCallRecord> {
    Ok(ApiLlmCallRecord {
        id: row.get(0)?,
        request_id: row.get(1)?,
        provider: row.get(2)?,
        model: row.get(3)?,
        endpoint: row.get(4)?,
        tokens_prompt: row.get(5)?,
        tokens_completion: row.get(6)?,
        cost_usd: row.get(7)?,
        latency_ms: row.get(8)?,
        status: row.get(9)?,
        error_text: row.get(10)?,
        error_context_json: parse_json_opt(row.get::<_, Option<String>>(11)?)
            .map_err(to_sql_err)?,
        created_at: row.get(12)?,
        updated_at: row.get(13)?,
    })
}

fn map_audio_generation_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<AudioGenerationRecord> {
    Ok(AudioGenerationRecord {
        id: row.get(0)?,
        summary_id: row.get(1)?,
        provider: row.get(2)?,
        voice_id: row.get(3)?,
        model: row.get(4)?,
        file_path: row.get(5)?,
        file_size_bytes: row.get(6)?,
        duration_sec: row.get(7)?,
        char_count: row.get(8)?,
        source_field: row.get(9)?,
        language: row.get(10)?,
        status: row.get(11)?,
        error_text: row.get(12)?,
        latency_ms: row.get(13)?,
        created_at: row.get(14)?,
    })
}

fn map_user_device_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<UserDeviceRecord> {
    Ok(UserDeviceRecord {
        id: row.get(0)?,
        user_id: row.get(1)?,
        token: row.get(2)?,
        platform: row.get(3)?,
        device_id: row.get(4)?,
        is_active: row.get(5)?,
        last_seen_at: row.get(6)?,
        created_at: row.get(7)?,
    })
}

fn parse_json_opt(raw: Option<String>) -> Result<Option<Value>, PersistenceError> {
    match raw {
        Some(text) if !text.trim().is_empty() => Ok(Some(serde_json::from_str(&text)?)),
        _ => Ok(None),
    }
}

fn to_sql_err(error: PersistenceError) -> rusqlite::Error {
    rusqlite::Error::FromSqlConversionFailure(0, rusqlite::types::Type::Text, Box::new(error))
}

fn bool_to_int(value: bool) -> i64 {
    if value {
        1
    } else {
        0
    }
}

fn normalize_optional_text(value: Option<&str>) -> Option<&str> {
    value.and_then(|raw| {
        let trimmed = raw.trim();
        (!trimmed.is_empty()).then_some(trimmed)
    })
}
