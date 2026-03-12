use rusqlite::Connection;
use serde_json::json;

use bsr_persistence::{
    create_minimal_request, create_request, get_crawl_result_by_request, get_request_by_dedupe_hash,
    get_request_by_forward, get_summary_by_request, insert_crawl_result, insert_llm_call,
    open_connection, update_request_error, update_request_lang_detected, update_request_status,
    update_summary_insights, upsert_summary, CreateRequestInput, InsertCrawlResultInput,
    InsertLlmCallInput, MinimalRequestInput, RequestErrorUpdate, UpsertSummaryInput,
};

fn create_processing_schema(connection: &Connection) {
    connection
        .execute_batch(
            r#"
            CREATE TABLE requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL DEFAULT 'url',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending',
                correlation_id TEXT,
                chat_id BIGINT,
                user_id BIGINT,
                input_url TEXT,
                normalized_url TEXT,
                dedupe_hash TEXT UNIQUE,
                input_message_id INTEGER,
                fwd_from_chat_id BIGINT,
                fwd_from_msg_id INTEGER,
                lang_detected TEXT,
                content_text TEXT,
                route_version INTEGER NOT NULL DEFAULT 1,
                server_version BIGINT NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at DATETIME,
                error_type TEXT,
                error_message TEXT,
                error_timestamp DATETIME,
                processing_time_ms INTEGER,
                error_context_json TEXT
            );
            CREATE TABLE summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL UNIQUE,
                lang TEXT,
                json_payload TEXT,
                insights_json TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                server_version BIGINT NOT NULL DEFAULT 1,
                is_read INTEGER NOT NULL DEFAULT 0,
                is_favorited INTEGER NOT NULL DEFAULT 0,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at DATETIME,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                provider TEXT,
                model TEXT,
                endpoint TEXT,
                request_headers_json TEXT,
                request_messages_json TEXT,
                response_text TEXT,
                response_json TEXT,
                openrouter_response_text TEXT,
                openrouter_response_json TEXT,
                tokens_prompt INTEGER,
                tokens_completion INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                status TEXT,
                error_text TEXT,
                structured_output_used INTEGER,
                structured_output_mode TEXT,
                error_context_json TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                server_version BIGINT NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at DATETIME
            );
            CREATE TABLE crawl_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL UNIQUE,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_url TEXT,
                endpoint TEXT,
                http_status INTEGER,
                status TEXT,
                options_json TEXT,
                correlation_id TEXT,
                content_markdown TEXT,
                content_html TEXT,
                structured_json TEXT,
                metadata_json TEXT,
                links_json TEXT,
                screenshots_paths_json TEXT,
                firecrawl_success INTEGER,
                firecrawl_error_code TEXT,
                firecrawl_error_message TEXT,
                firecrawl_details_json TEXT,
                raw_response_json TEXT,
                latency_ms INTEGER,
                error_text TEXT,
                server_version BIGINT NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at DATETIME
            );
            "#,
        )
        .expect("create processing schema");
}

#[test]
fn request_creation_and_dedupe_parity_hold() {
    let dir = tempfile::TempDir::new().expect("temp dir");
    let connection = open_connection(dir.path().join("app.db")).expect("open db");
    create_processing_schema(&connection);

    let created = create_request(
        &connection,
        &CreateRequestInput {
            request_type: "url".to_string(),
            status: "pending".to_string(),
            correlation_id: Some("cid-1".to_string()),
            chat_id: Some(10),
            user_id: Some(20),
            input_url: Some("https://example.com".to_string()),
            normalized_url: Some("https://example.com".to_string()),
            dedupe_hash: Some("hash".to_string()),
            input_message_id: Some(30),
            fwd_from_chat_id: None,
            fwd_from_msg_id: None,
            lang_detected: None,
            content_text: None,
            route_version: 1,
        },
    )
    .expect("create request");

    let deduped = create_request(
        &connection,
        &CreateRequestInput {
            correlation_id: Some("cid-2".to_string()),
            status: "ok".to_string(),
            content_text: Some("body".to_string()),
            ..CreateRequestInput {
                request_type: "url".to_string(),
                status: "pending".to_string(),
                correlation_id: Some("cid-1".to_string()),
                chat_id: Some(10),
                user_id: Some(20),
                input_url: Some("https://example.com".to_string()),
                normalized_url: Some("https://example.com".to_string()),
                dedupe_hash: Some("hash".to_string()),
                input_message_id: Some(30),
                fwd_from_chat_id: None,
                fwd_from_msg_id: None,
                lang_detected: None,
                content_text: None,
                route_version: 1,
            }
        },
    )
    .expect("dedupe request");

    assert_eq!(created.id, deduped.id);
    assert_eq!(deduped.correlation_id.as_deref(), Some("cid-2"));
    assert_eq!(deduped.status, "ok");
    assert_eq!(deduped.content_text.as_deref(), Some("body"));

    let fetched = get_request_by_dedupe_hash(&connection, "hash")
        .expect("fetch by hash")
        .expect("request by hash");
    assert_eq!(fetched.id, created.id);
}

#[test]
fn forward_lookup_and_summary_upsert_match_processing_expectations() {
    let dir = tempfile::TempDir::new().expect("temp dir");
    let connection = open_connection(dir.path().join("app.db")).expect("open db");
    create_processing_schema(&connection);

    let request = create_request(
        &connection,
        &CreateRequestInput {
            request_type: "forward".to_string(),
            status: "pending".to_string(),
            correlation_id: Some("cid-forward".to_string()),
            chat_id: Some(10),
            user_id: Some(20),
            input_url: None,
            normalized_url: None,
            dedupe_hash: None,
            input_message_id: Some(55),
            fwd_from_chat_id: Some(777),
            fwd_from_msg_id: Some(888),
            lang_detected: Some("en".to_string()),
            content_text: Some("forward body".to_string()),
            route_version: 1,
        },
    )
    .expect("create forward request");

    let looked_up = get_request_by_forward(&connection, 777, 888)
        .expect("lookup forward")
        .expect("forward request");
    assert_eq!(looked_up.id, request.id);

    let summary = upsert_summary(
        &connection,
        &UpsertSummaryInput {
            request_id: request.id,
            lang: "en".to_string(),
            json_payload: json!({"summary_250": "short", "summary_1000": "long", "tldr": "full"}),
            insights_json: None,
            is_read: true,
        },
    )
    .expect("insert summary");
    assert_eq!(summary.version, 1);

    update_summary_insights(&connection, request.id, &json!({"new_facts": ["x"]}))
        .expect("update insights");

    let updated = get_summary_by_request(&connection, request.id)
        .expect("fetch summary")
        .expect("summary row");
    assert_eq!(updated.version, 1);
    assert_eq!(
        updated.insights_json.expect("insights"),
        json!({"new_facts": ["x"]})
    );
}

#[test]
fn minimal_request_error_llm_and_crawl_persistence_roundtrip() {
    let dir = tempfile::TempDir::new().expect("temp dir");
    let connection = open_connection(dir.path().join("app.db")).expect("open db");
    create_processing_schema(&connection);

    let (request, is_new) = create_minimal_request(
        &connection,
        &MinimalRequestInput {
            request_type: "url".to_string(),
            status: "pending".to_string(),
            correlation_id: Some("cid-min".to_string()),
            chat_id: Some(1),
            user_id: Some(2),
            input_url: Some("https://example.com/article".to_string()),
            normalized_url: Some("https://example.com/article".to_string()),
            dedupe_hash: Some("hash-min".to_string()),
        },
    )
    .expect("create minimal request");
    assert!(is_new);

    update_request_lang_detected(&connection, request.id, "ru").expect("update lang");
    update_request_status(&connection, request.id, "extracting").expect("update status");
    update_request_error(
        &connection,
        request.id,
        &RequestErrorUpdate {
            status: "error".to_string(),
            error_type: Some("FIRECRAWL_ERROR".to_string()),
            error_message: Some("boom".to_string()),
            processing_time_ms: Some(123),
            error_context_json: Some(json!({"stage": "extraction"})),
        },
    )
    .expect("update error");

    let crawl = insert_crawl_result(
        &connection,
        &InsertCrawlResultInput {
            request_id: request.id,
            firecrawl_success: false,
            source_url: Some("https://example.com/article".to_string()),
            endpoint: Some("/v2/scrape".to_string()),
            http_status: Some(500),
            status: Some("error".to_string()),
            options_json: Some(json!({"mobile": true})),
            correlation_id: Some("cid-min".to_string()),
            content_markdown: None,
            content_html: None,
            structured_json: None,
            metadata_json: Some(json!({"title": "Article"})),
            links_json: None,
            firecrawl_error_code: Some("upstream_error".to_string()),
            firecrawl_error_message: Some("bad".to_string()),
            firecrawl_details_json: Some(json!({"details": ["x"]})),
            raw_response_json: Some(json!({"success": false})),
            latency_ms: Some(250),
            error_text: Some("bad".to_string()),
        },
    )
    .expect("insert crawl result");

    let llm_call_id = insert_llm_call(
        &connection,
        &InsertLlmCallInput {
            request_id: request.id,
            provider: Some("openrouter".to_string()),
            model: Some("model".to_string()),
            endpoint: Some("/api/v1/chat/completions".to_string()),
            request_headers_json: Some(json!({"authorization": "***"})),
            request_messages_json: Some(json!([{"role": "system", "content": "sys"}])),
            response_text: None,
            response_json: None,
            openrouter_response_text: Some("{\"ok\":true}".to_string()),
            openrouter_response_json: Some(json!({"ok": true})),
            tokens_prompt: Some(11),
            tokens_completion: Some(22),
            cost_usd: Some(0.12),
            latency_ms: Some(333),
            status: Some("ok".to_string()),
            error_text: None,
            structured_output_used: Some(true),
            structured_output_mode: Some("json_schema".to_string()),
            error_context_json: None,
        },
    )
    .expect("insert llm call");

    assert!(llm_call_id > 0);
    let fetched_crawl = get_crawl_result_by_request(&connection, request.id)
        .expect("fetch crawl")
        .expect("crawl row");
    assert_eq!(fetched_crawl.id, crawl.id);
    assert_eq!(fetched_crawl.http_status, Some(500));
}
