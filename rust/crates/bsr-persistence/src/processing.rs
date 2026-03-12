use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::PersistenceError;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RequestRecord {
    pub id: i64,
    pub request_type: String,
    pub status: String,
    pub correlation_id: Option<String>,
    pub chat_id: Option<i64>,
    pub user_id: Option<i64>,
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
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SummaryRecord {
    pub id: i64,
    pub request_id: i64,
    pub lang: Option<String>,
    pub json_payload: Option<Value>,
    pub insights_json: Option<Value>,
    pub version: i64,
    pub is_read: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CrawlResultRecord {
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
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CreateRequestInput {
    pub request_type: String,
    pub status: String,
    pub correlation_id: Option<String>,
    pub chat_id: Option<i64>,
    pub user_id: Option<i64>,
    pub input_url: Option<String>,
    pub normalized_url: Option<String>,
    pub dedupe_hash: Option<String>,
    pub input_message_id: Option<i64>,
    pub fwd_from_chat_id: Option<i64>,
    pub fwd_from_msg_id: Option<i64>,
    pub lang_detected: Option<String>,
    pub content_text: Option<String>,
    pub route_version: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MinimalRequestInput {
    pub request_type: String,
    pub status: String,
    pub correlation_id: Option<String>,
    pub chat_id: Option<i64>,
    pub user_id: Option<i64>,
    pub input_url: Option<String>,
    pub normalized_url: Option<String>,
    pub dedupe_hash: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RequestErrorUpdate {
    pub status: String,
    pub error_type: Option<String>,
    pub error_message: Option<String>,
    pub processing_time_ms: Option<i64>,
    pub error_context_json: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UpsertSummaryInput {
    pub request_id: i64,
    pub lang: String,
    pub json_payload: Value,
    pub insights_json: Option<Value>,
    pub is_read: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InsertLlmCallInput {
    pub request_id: i64,
    pub provider: Option<String>,
    pub model: Option<String>,
    pub endpoint: Option<String>,
    pub request_headers_json: Option<Value>,
    pub request_messages_json: Option<Value>,
    pub response_text: Option<String>,
    pub response_json: Option<Value>,
    pub openrouter_response_text: Option<String>,
    pub openrouter_response_json: Option<Value>,
    pub tokens_prompt: Option<i64>,
    pub tokens_completion: Option<i64>,
    pub cost_usd: Option<f64>,
    pub latency_ms: Option<i64>,
    pub status: Option<String>,
    pub error_text: Option<String>,
    pub structured_output_used: Option<bool>,
    pub structured_output_mode: Option<String>,
    pub error_context_json: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InsertCrawlResultInput {
    pub request_id: i64,
    pub firecrawl_success: bool,
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
    pub firecrawl_error_code: Option<String>,
    pub firecrawl_error_message: Option<String>,
    pub firecrawl_details_json: Option<Value>,
    pub raw_response_json: Option<Value>,
    pub latency_ms: Option<i64>,
    pub error_text: Option<String>,
}

pub fn get_request_by_dedupe_hash(
    connection: &Connection,
    dedupe_hash: &str,
) -> Result<Option<RequestRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, type, status, correlation_id, chat_id, user_id, input_url, normalized_url,
               dedupe_hash, input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected,
               content_text, route_version, error_type, error_message, processing_time_ms,
               error_context_json
        FROM requests
        WHERE dedupe_hash = ?1
        "#,
    )?;
    statement
        .query_row([dedupe_hash], map_request_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_request_by_forward(
    connection: &Connection,
    fwd_from_chat_id: i64,
    fwd_from_msg_id: i64,
) -> Result<Option<RequestRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, type, status, correlation_id, chat_id, user_id, input_url, normalized_url,
               dedupe_hash, input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected,
               content_text, route_version, error_type, error_message, processing_time_ms,
               error_context_json
        FROM requests
        WHERE fwd_from_chat_id = ?1 AND fwd_from_msg_id = ?2
        "#,
    )?;
    statement
        .query_row(params![fwd_from_chat_id, fwd_from_msg_id], map_request_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_request_by_id(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<RequestRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, type, status, correlation_id, chat_id, user_id, input_url, normalized_url,
               dedupe_hash, input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected,
               content_text, route_version, error_type, error_message, processing_time_ms,
               error_context_json
        FROM requests
        WHERE id = ?1
        "#,
    )?;
    statement
        .query_row([request_id], map_request_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn create_request(
    connection: &Connection,
    input: &CreateRequestInput,
) -> Result<RequestRecord, PersistenceError> {
    let execute_insert = || {
        connection.execute(
            r#"
            INSERT INTO requests (
                type, status, correlation_id, chat_id, user_id, input_url, normalized_url,
                dedupe_hash, input_message_id, fwd_from_chat_id, fwd_from_msg_id, lang_detected,
                content_text, route_version
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)
            "#,
            params![
                input.request_type,
                input.status,
                input.correlation_id,
                input.chat_id,
                input.user_id,
                input.input_url,
                input.normalized_url,
                input.dedupe_hash,
                input.input_message_id,
                input.fwd_from_chat_id,
                input.fwd_from_msg_id,
                input.lang_detected,
                input.content_text,
                input.route_version,
            ],
        )
    };

    match execute_insert() {
        Ok(_) => {
            let request_id = connection.last_insert_rowid();
            get_request_by_id(connection, request_id)?
                .ok_or_else(|| PersistenceError::MissingRow("created request".to_string()))
        }
        Err(rusqlite::Error::SqliteFailure(error, _))
            if error.code == rusqlite::ErrorCode::ConstraintViolation =>
        {
            if let Some(dedupe_hash) = input.dedupe_hash.as_deref() {
                connection.execute(
                    r#"
                    UPDATE requests
                    SET correlation_id = ?2,
                        status = ?3,
                        chat_id = ?4,
                        user_id = ?5,
                        input_url = ?6,
                        normalized_url = ?7,
                        input_message_id = ?8,
                        fwd_from_chat_id = ?9,
                        fwd_from_msg_id = ?10,
                        lang_detected = ?11,
                        content_text = ?12,
                        route_version = ?13
                    WHERE dedupe_hash = ?1
                    "#,
                    params![
                        dedupe_hash,
                        input.correlation_id,
                        input.status,
                        input.chat_id,
                        input.user_id,
                        input.input_url,
                        input.normalized_url,
                        input.input_message_id,
                        input.fwd_from_chat_id,
                        input.fwd_from_msg_id,
                        input.lang_detected,
                        input.content_text,
                        input.route_version,
                    ],
                )?;
                return get_request_by_dedupe_hash(connection, dedupe_hash)?.ok_or_else(|| {
                    PersistenceError::MissingRow("dedupe-updated request".to_string())
                });
            }
            Err(PersistenceError::Sqlite(rusqlite::Error::SqliteFailure(
                error, None,
            )))
        }
        Err(err) => Err(PersistenceError::Sqlite(err)),
    }
}

pub fn create_minimal_request(
    connection: &Connection,
    input: &MinimalRequestInput,
) -> Result<(RequestRecord, bool), PersistenceError> {
    let insert_result = connection.execute(
        r#"
        INSERT INTO requests (
            type, status, correlation_id, chat_id, user_id, input_url, normalized_url, dedupe_hash
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)
        "#,
        params![
            input.request_type,
            input.status,
            input.correlation_id,
            input.chat_id,
            input.user_id,
            input.input_url,
            input.normalized_url,
            input.dedupe_hash,
        ],
    );

    match insert_result {
        Ok(_) => {
            let request_id = connection.last_insert_rowid();
            let record = get_request_by_id(connection, request_id)?
                .ok_or_else(|| PersistenceError::MissingRow("created minimal request".to_string()))?;
            Ok((record, true))
        }
        Err(rusqlite::Error::SqliteFailure(error, _))
            if error.code == rusqlite::ErrorCode::ConstraintViolation =>
        {
            if let Some(dedupe_hash) = input.dedupe_hash.as_deref() {
                let existing = get_request_by_dedupe_hash(connection, dedupe_hash)?.ok_or_else(|| {
                    PersistenceError::MissingRow("dedupe-existing minimal request".to_string())
                })?;
                Ok((existing, false))
            } else {
                Err(PersistenceError::Sqlite(rusqlite::Error::SqliteFailure(
                    error, None,
                )))
            }
        }
        Err(err) => Err(PersistenceError::Sqlite(err)),
    }
}

pub fn update_request_status(
    connection: &Connection,
    request_id: i64,
    status: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        "UPDATE requests SET status = ?2 WHERE id = ?1",
        params![request_id, status],
    )?;
    Ok(())
}

pub fn update_request_correlation_id(
    connection: &Connection,
    request_id: i64,
    correlation_id: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        "UPDATE requests SET correlation_id = ?2 WHERE id = ?1",
        params![request_id, correlation_id],
    )?;
    Ok(())
}

pub fn update_request_lang_detected(
    connection: &Connection,
    request_id: i64,
    lang_detected: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        "UPDATE requests SET lang_detected = ?2 WHERE id = ?1",
        params![request_id, lang_detected],
    )?;
    Ok(())
}

pub fn update_request_error(
    connection: &Connection,
    request_id: i64,
    update: &RequestErrorUpdate,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE requests
        SET status = ?2,
            error_type = ?3,
            error_message = ?4,
            processing_time_ms = ?5,
            error_context_json = ?6,
            error_timestamp = CURRENT_TIMESTAMP
        WHERE id = ?1
        "#,
        params![
            request_id,
            update.status,
            update.error_type,
            update.error_message,
            update.processing_time_ms,
            to_json_text(update.error_context_json.as_ref())?,
        ],
    )?;
    Ok(())
}

pub fn get_summary_by_request(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<SummaryRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, lang, json_payload, insights_json, version, is_read
        FROM summaries
        WHERE request_id = ?1
        "#,
    )?;
    statement
        .query_row([request_id], map_summary_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_unread_summary_by_request(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<SummaryRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, lang, json_payload, insights_json, version, is_read
        FROM summaries
        WHERE request_id = ?1 AND is_read = 0
        "#,
    )?;
    statement
        .query_row([request_id], map_summary_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn upsert_summary(
    connection: &Connection,
    input: &UpsertSummaryInput,
) -> Result<SummaryRecord, PersistenceError> {
    let insert_result = connection.execute(
        r#"
        INSERT INTO summaries (request_id, lang, json_payload, insights_json, is_read, version)
        VALUES (?1, ?2, ?3, ?4, ?5, 1)
        "#,
        params![
            input.request_id,
            input.lang,
            to_json_text(Some(&input.json_payload))?,
            to_json_text(input.insights_json.as_ref())?,
            input.is_read,
        ],
    );

    match insert_result {
        Ok(_) => {}
        Err(rusqlite::Error::SqliteFailure(error, _))
            if error.code == rusqlite::ErrorCode::ConstraintViolation =>
        {
            connection.execute(
                r#"
                UPDATE summaries
                SET lang = ?2,
                    json_payload = ?3,
                    insights_json = ?4,
                    is_read = ?5,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?1
                "#,
                params![
                    input.request_id,
                    input.lang,
                    to_json_text(Some(&input.json_payload))?,
                    to_json_text(input.insights_json.as_ref())?,
                    input.is_read,
                ],
            )?;
        }
        Err(err) => return Err(PersistenceError::Sqlite(err)),
    }

    get_summary_by_request(connection, input.request_id)?
        .ok_or_else(|| PersistenceError::MissingRow("upserted summary".to_string()))
}

pub fn update_summary_insights(
    connection: &Connection,
    request_id: i64,
    insights_json: &Value,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE summaries
        SET insights_json = ?2
        WHERE request_id = ?1
        "#,
        params![request_id, to_json_text(Some(insights_json))?],
    )?;
    Ok(())
}

pub fn insert_llm_call(
    connection: &Connection,
    input: &InsertLlmCallInput,
) -> Result<i64, PersistenceError> {
    connection.execute(
        r#"
        INSERT INTO llm_calls (
            request_id, provider, model, endpoint, request_headers_json, request_messages_json,
            response_text, response_json, openrouter_response_text, openrouter_response_json,
            tokens_prompt, tokens_completion, cost_usd, latency_ms, status, error_text,
            structured_output_used, structured_output_mode, error_context_json
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19)
        "#,
        params![
            input.request_id,
            input.provider,
            input.model,
            input.endpoint,
            to_json_text(input.request_headers_json.as_ref())?,
            to_json_text(input.request_messages_json.as_ref())?,
            input.response_text,
            to_json_text(input.response_json.as_ref())?,
            input.openrouter_response_text,
            to_json_text(input.openrouter_response_json.as_ref())?,
            input.tokens_prompt,
            input.tokens_completion,
            input.cost_usd,
            input.latency_ms,
            input.status,
            input.error_text,
            input.structured_output_used,
            input.structured_output_mode,
            to_json_text(input.error_context_json.as_ref())?,
        ],
    )?;
    Ok(connection.last_insert_rowid())
}

pub fn insert_crawl_result(
    connection: &Connection,
    input: &InsertCrawlResultInput,
) -> Result<CrawlResultRecord, PersistenceError> {
    let insert_result = connection.execute(
        r#"
        INSERT INTO crawl_results (
            request_id, source_url, endpoint, http_status, status, options_json, correlation_id,
            content_markdown, content_html, structured_json, metadata_json, links_json,
            firecrawl_success, firecrawl_error_code, firecrawl_error_message, firecrawl_details_json,
            raw_response_json, latency_ms, error_text
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19)
        "#,
        params![
            input.request_id,
            input.source_url,
            input.endpoint,
            input.http_status,
            input.status,
            to_json_text(input.options_json.as_ref())?,
            input.correlation_id,
            input.content_markdown,
            input.content_html,
            to_json_text(input.structured_json.as_ref())?,
            to_json_text(input.metadata_json.as_ref())?,
            to_json_text(input.links_json.as_ref())?,
            input.firecrawl_success,
            input.firecrawl_error_code,
            input.firecrawl_error_message,
            to_json_text(input.firecrawl_details_json.as_ref())?,
            to_json_text(input.raw_response_json.as_ref())?,
            input.latency_ms,
            input.error_text,
        ],
    );

    match insert_result {
        Ok(_) => {}
        Err(rusqlite::Error::SqliteFailure(error, _))
            if error.code == rusqlite::ErrorCode::ConstraintViolation => {}
        Err(err) => return Err(PersistenceError::Sqlite(err)),
    }

    get_crawl_result_by_request(connection, input.request_id)?
        .ok_or_else(|| PersistenceError::MissingRow("crawl result".to_string()))
}

pub fn get_crawl_result_by_request(
    connection: &Connection,
    request_id: i64,
) -> Result<Option<CrawlResultRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, request_id, source_url, endpoint, http_status, status, options_json,
               correlation_id, content_markdown, content_html, structured_json, metadata_json,
               links_json, firecrawl_success, firecrawl_error_code, firecrawl_error_message,
               firecrawl_details_json, raw_response_json, latency_ms, error_text
        FROM crawl_results
        WHERE request_id = ?1
        "#,
    )?;
    statement
        .query_row([request_id], map_crawl_result_row)
        .optional()
        .map_err(PersistenceError::from)
}

fn map_request_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RequestRecord> {
    Ok(RequestRecord {
        id: row.get(0)?,
        request_type: row.get(1)?,
        status: row.get(2)?,
        correlation_id: row.get(3)?,
        chat_id: row.get(4)?,
        user_id: row.get(5)?,
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
        error_context_json: parse_json_opt(row.get::<_, Option<String>>(18)?).map_err(to_sql_err)?,
    })
}

fn map_summary_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<SummaryRecord> {
    Ok(SummaryRecord {
        id: row.get(0)?,
        request_id: row.get(1)?,
        lang: row.get(2)?,
        json_payload: parse_json_opt(row.get::<_, Option<String>>(3)?).map_err(to_sql_err)?,
        insights_json: parse_json_opt(row.get::<_, Option<String>>(4)?).map_err(to_sql_err)?,
        version: row.get(5)?,
        is_read: row.get(6)?,
    })
}

fn map_crawl_result_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<CrawlResultRecord> {
    Ok(CrawlResultRecord {
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
    })
}

fn parse_json_opt(raw: Option<String>) -> Result<Option<Value>, PersistenceError> {
    match raw {
        Some(text) if !text.trim().is_empty() => Ok(Some(serde_json::from_str(&text)?)),
        _ => Ok(None),
    }
}

fn to_json_text(value: Option<&Value>) -> Result<Option<String>, PersistenceError> {
    value.map(serde_json::to_string).transpose().map_err(PersistenceError::from)
}

fn to_sql_err(error: PersistenceError) -> rusqlite::Error {
    rusqlite::Error::FromSqlConversionFailure(
        0,
        rusqlite::types::Type::Text,
        Box::new(error),
    )
}
