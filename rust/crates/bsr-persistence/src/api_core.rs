use chrono::{DateTime, Duration, Utc};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::PersistenceError;

const DB_INFO_TABLE_ALLOWLIST: &[&str] = &[
    "audit_logs",
    "batch_sessions",
    "chats",
    "client_secrets",
    "collection_collaborators",
    "collection_invites",
    "collections",
    "crawl_results",
    "digest_categories",
    "digest_channel_subscriptions",
    "digest_deliveries",
    "digest_post_candidates",
    "digest_preferences",
    "digest_topic_rules",
    "digest_trigger_records",
    "karakeep_sync",
    "llm_calls",
    "migration_history",
    "refresh_tokens",
    "requests",
    "summaries",
    "summary_embeddings",
    "telegram_messages",
    "topic_search_index",
    "user_interactions",
    "users",
    "video_downloads",
];

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UserRecord {
    pub telegram_user_id: i64,
    pub username: Option<String>,
    pub is_owner: bool,
    pub preferences_json: Option<Value>,
    pub linked_telegram_user_id: Option<i64>,
    pub linked_telegram_username: Option<String>,
    pub linked_telegram_photo_url: Option<String>,
    pub linked_telegram_first_name: Option<String>,
    pub linked_telegram_last_name: Option<String>,
    pub linked_at: Option<String>,
    pub link_nonce: Option<String>,
    pub link_nonce_expires_at: Option<String>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RefreshTokenRecord {
    pub id: i64,
    pub user_id: i64,
    pub token_hash: String,
    pub client_id: Option<String>,
    pub device_info: Option<String>,
    pub ip_address: Option<String>,
    pub is_revoked: bool,
    pub expires_at: String,
    pub last_used_at: Option<String>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ClientSecretRecord {
    pub id: i64,
    pub user_id: i64,
    pub client_id: String,
    pub secret_hash: String,
    pub secret_salt: String,
    pub status: String,
    pub label: Option<String>,
    pub description: Option<String>,
    pub expires_at: Option<String>,
    pub last_used_at: Option<String>,
    pub failed_attempts: i64,
    pub locked_until: Option<String>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UserSummaryStatRow {
    pub summary_id: i64,
    pub lang: Option<String>,
    pub is_read: bool,
    pub json_payload_raw: Option<String>,
    pub request_normalized_url: Option<String>,
    pub request_created_at: Option<String>,
}

pub fn get_user_by_telegram_id(
    connection: &Connection,
    telegram_user_id: i64,
) -> Result<Option<UserRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT telegram_user_id, username, is_owner, preferences_json, linked_telegram_user_id,
               linked_telegram_username, linked_telegram_photo_url, linked_telegram_first_name,
               linked_telegram_last_name, linked_at, link_nonce, link_nonce_expires_at,
               created_at, updated_at
        FROM users
        WHERE telegram_user_id = ?1
        "#,
    )?;
    statement
        .query_row([telegram_user_id], map_user_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_or_create_user(
    connection: &Connection,
    telegram_user_id: i64,
    username: Option<&str>,
    is_owner: bool,
) -> Result<(UserRecord, bool), PersistenceError> {
    if let Some(existing) = get_user_by_telegram_id(connection, telegram_user_id)? {
        return Ok((existing, false));
    }

    let now = utc_now_text();
    let server_version = next_server_version();
    connection.execute(
        r#"
        INSERT INTO users (
            telegram_user_id, username, is_owner, server_version, updated_at, created_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?5)
        "#,
        params![telegram_user_id, username, is_owner, server_version, now],
    )?;

    let user = get_user_by_telegram_id(connection, telegram_user_id)?
        .ok_or_else(|| PersistenceError::MissingRow("created user".to_string()))?;
    Ok((user, true))
}

pub fn delete_user(connection: &Connection, telegram_user_id: i64) -> Result<(), PersistenceError> {
    connection.execute(
        "DELETE FROM users WHERE telegram_user_id = ?1",
        [telegram_user_id],
    )?;
    Ok(())
}

pub fn update_user_preferences(
    connection: &Connection,
    telegram_user_id: i64,
    preferences_json: &Value,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE users
        SET preferences_json = ?2,
            server_version = ?3,
            updated_at = ?4
        WHERE telegram_user_id = ?1
        "#,
        params![
            telegram_user_id,
            serde_json::to_string(preferences_json)?,
            next_server_version(),
            now
        ],
    )?;
    Ok(())
}

pub fn set_link_nonce(
    connection: &Connection,
    telegram_user_id: i64,
    nonce: &str,
    expires_at: &str,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE users
        SET link_nonce = ?2,
            link_nonce_expires_at = ?3,
            server_version = ?4,
            updated_at = ?5
        WHERE telegram_user_id = ?1
        "#,
        params![
            telegram_user_id,
            nonce,
            expires_at,
            next_server_version(),
            now
        ],
    )?;
    Ok(())
}

pub fn clear_link_nonce(
    connection: &Connection,
    telegram_user_id: i64,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE users
        SET link_nonce = NULL,
            link_nonce_expires_at = NULL,
            server_version = ?2,
            updated_at = ?3
        WHERE telegram_user_id = ?1
        "#,
        params![telegram_user_id, next_server_version(), now],
    )?;
    Ok(())
}

pub fn complete_telegram_link(
    connection: &Connection,
    telegram_user_id: i64,
    linked_telegram_user_id: i64,
    username: Option<&str>,
    photo_url: Option<&str>,
    first_name: Option<&str>,
    last_name: Option<&str>,
    linked_at: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE users
        SET linked_telegram_user_id = ?2,
            linked_telegram_username = ?3,
            linked_telegram_photo_url = ?4,
            linked_telegram_first_name = ?5,
            linked_telegram_last_name = ?6,
            linked_at = ?7,
            link_nonce = NULL,
            link_nonce_expires_at = NULL,
            server_version = ?8,
            updated_at = ?7
        WHERE telegram_user_id = ?1
        "#,
        params![
            telegram_user_id,
            linked_telegram_user_id,
            username,
            photo_url,
            first_name,
            last_name,
            linked_at,
            next_server_version(),
        ],
    )?;
    Ok(())
}

pub fn unlink_telegram(
    connection: &Connection,
    telegram_user_id: i64,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE users
        SET linked_telegram_user_id = NULL,
            linked_telegram_username = NULL,
            linked_telegram_photo_url = NULL,
            linked_telegram_first_name = NULL,
            linked_telegram_last_name = NULL,
            linked_at = NULL,
            link_nonce = NULL,
            link_nonce_expires_at = NULL,
            server_version = ?2,
            updated_at = ?3
        WHERE telegram_user_id = ?1
        "#,
        params![telegram_user_id, next_server_version(), now],
    )?;
    Ok(())
}

pub fn create_refresh_token(
    connection: &Connection,
    user_id: i64,
    token_hash: &str,
    client_id: Option<&str>,
    device_info: Option<&str>,
    ip_address: Option<&str>,
    expires_at: &str,
) -> Result<RefreshTokenRecord, PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        INSERT INTO refresh_tokens (
            user_id, token_hash, client_id, device_info, ip_address, is_revoked,
            expires_at, last_used_at, created_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6, ?7, ?7)
        "#,
        params![
            user_id,
            token_hash,
            client_id,
            device_info,
            ip_address,
            expires_at,
            now
        ],
    )?;
    let id = connection.last_insert_rowid();
    get_refresh_token_by_id(connection, id)?
        .ok_or_else(|| PersistenceError::MissingRow("created refresh token".to_string()))
}

pub fn get_refresh_token_by_hash(
    connection: &Connection,
    token_hash: &str,
) -> Result<Option<RefreshTokenRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, token_hash, client_id, device_info, ip_address, is_revoked,
               expires_at, last_used_at, created_at
        FROM refresh_tokens
        WHERE token_hash = ?1
        "#,
    )?;
    statement
        .query_row([token_hash], map_refresh_token_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn revoke_refresh_token(
    connection: &Connection,
    token_hash: &str,
) -> Result<bool, PersistenceError> {
    let updated = connection.execute(
        r#"
        UPDATE refresh_tokens
        SET is_revoked = 1
        WHERE token_hash = ?1
        "#,
        [token_hash],
    )?;
    Ok(updated > 0)
}

pub fn update_refresh_token_last_used(
    connection: &Connection,
    token_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        "UPDATE refresh_tokens SET last_used_at = ?2 WHERE id = ?1",
        params![token_id, utc_now_text()],
    )?;
    Ok(())
}

pub fn list_active_sessions(
    connection: &Connection,
    user_id: i64,
    now: &str,
) -> Result<Vec<RefreshTokenRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, token_hash, client_id, device_info, ip_address, is_revoked,
               expires_at, last_used_at, created_at
        FROM refresh_tokens
        WHERE user_id = ?1
          AND is_revoked = 0
          AND expires_at > ?2
        ORDER BY last_used_at DESC
        "#,
    )?;
    let rows = statement.query_map(params![user_id, now], map_refresh_token_row)?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn get_client_secret(
    connection: &Connection,
    user_id: i64,
    client_id: &str,
) -> Result<Option<ClientSecretRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, client_id, secret_hash, secret_salt, status, label, description,
               expires_at, last_used_at, failed_attempts, locked_until, created_at, updated_at
        FROM client_secrets
        WHERE user_id = ?1 AND client_id = ?2
        ORDER BY created_at DESC
        LIMIT 1
        "#,
    )?;
    statement
        .query_row(params![user_id, client_id], map_client_secret_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_client_secret_by_id(
    connection: &Connection,
    key_id: i64,
) -> Result<Option<ClientSecretRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, client_id, secret_hash, secret_salt, status, label, description,
               expires_at, last_used_at, failed_attempts, locked_until, created_at, updated_at
        FROM client_secrets
        WHERE id = ?1
        "#,
    )?;
    statement
        .query_row([key_id], map_client_secret_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn create_client_secret(
    connection: &Connection,
    user_id: i64,
    client_id: &str,
    secret_hash: &str,
    secret_salt: &str,
    status: &str,
    label: Option<&str>,
    description: Option<&str>,
    expires_at: Option<&str>,
) -> Result<ClientSecretRecord, PersistenceError> {
    let now = utc_now_text();
    let server_version = next_server_version();
    connection.execute(
        r#"
        INSERT INTO client_secrets (
            user_id, client_id, secret_hash, secret_salt, status, label, description,
            expires_at, failed_attempts, locked_until, server_version, updated_at, created_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 0, NULL, ?9, ?10, ?10)
        "#,
        params![
            user_id,
            client_id,
            secret_hash,
            secret_salt,
            status,
            label,
            description,
            expires_at,
            server_version,
            now,
        ],
    )?;
    let id = connection.last_insert_rowid();
    get_client_secret_by_id(connection, id)?
        .ok_or_else(|| PersistenceError::MissingRow("created client secret".to_string()))
}

pub fn revoke_active_secrets(
    connection: &Connection,
    user_id: i64,
    client_id: &str,
) -> Result<i64, PersistenceError> {
    let now = utc_now_text();
    let updated = connection.execute(
        r#"
        UPDATE client_secrets
        SET status = 'revoked',
            failed_attempts = 0,
            locked_until = NULL,
            server_version = ?3,
            updated_at = ?4
        WHERE user_id = ?1
          AND client_id = ?2
          AND status = 'active'
        "#,
        params![user_id, client_id, next_server_version(), now],
    )?;
    Ok(updated as i64)
}

pub fn rotate_client_secret(
    connection: &Connection,
    key_id: i64,
    secret_hash: &str,
    secret_salt: &str,
    label: Option<&str>,
    description: Option<&str>,
    expires_at: Option<&str>,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE client_secrets
        SET secret_hash = ?2,
            secret_salt = ?3,
            status = 'active',
            failed_attempts = 0,
            locked_until = NULL,
            expires_at = ?4,
            label = ?5,
            description = ?6,
            last_used_at = NULL,
            server_version = ?7,
            updated_at = ?8
        WHERE id = ?1
        "#,
        params![
            key_id,
            secret_hash,
            secret_salt,
            expires_at,
            label,
            description,
            next_server_version(),
            now,
        ],
    )?;
    Ok(())
}

pub fn mark_client_secret_revoked(
    connection: &Connection,
    key_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE client_secrets
        SET status = 'revoked',
            failed_attempts = 0,
            locked_until = NULL,
            server_version = ?2,
            updated_at = ?3
        WHERE id = ?1
        "#,
        params![key_id, next_server_version(), utc_now_text()],
    )?;
    Ok(())
}

pub fn set_client_secret_status(
    connection: &Connection,
    key_id: i64,
    status: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE client_secrets
        SET status = ?2,
            server_version = ?3,
            updated_at = ?4
        WHERE id = ?1
        "#,
        params![key_id, status, next_server_version(), utc_now_text()],
    )?;
    Ok(())
}

pub fn touch_client_secret_after_success(
    connection: &Connection,
    key_id: i64,
    last_used_at: &str,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE client_secrets
        SET last_used_at = ?2,
            status = 'active',
            server_version = ?3,
            updated_at = ?2
        WHERE id = ?1
        "#,
        params![key_id, last_used_at, next_server_version()],
    )?;
    Ok(())
}

pub fn list_client_secrets(
    connection: &Connection,
    user_id: Option<i64>,
    client_id: Option<&str>,
    status: Option<&str>,
) -> Result<Vec<ClientSecretRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, client_id, secret_hash, secret_salt, status, label, description,
               expires_at, last_used_at, failed_attempts, locked_until, created_at, updated_at
        FROM client_secrets
        WHERE (?1 IS NULL OR user_id = ?1)
          AND (?2 IS NULL OR client_id = ?2)
          AND (?3 IS NULL OR status = ?3)
        ORDER BY created_at DESC, id DESC
        "#,
    )?;
    let rows = statement.query_map(params![user_id, client_id, status], map_client_secret_row)?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn increment_failed_attempts(
    connection: &Connection,
    key_id: i64,
    max_attempts: i64,
    lockout_minutes: i64,
) -> Result<ClientSecretRecord, PersistenceError> {
    let record = get_client_secret_by_id(connection, key_id)?.ok_or_else(|| {
        PersistenceError::MissingRow("client secret for failed attempt".to_string())
    })?;
    let next_attempts = record.failed_attempts + 1;
    let (status, locked_until) = if next_attempts >= max_attempts {
        (
            "locked",
            Some((Utc::now() + Duration::minutes(lockout_minutes)).to_rfc3339()),
        )
    } else {
        (record.status.as_str(), record.locked_until.clone())
    };
    connection.execute(
        r#"
        UPDATE client_secrets
        SET failed_attempts = ?2,
            status = ?3,
            locked_until = ?4,
            server_version = ?5,
            updated_at = ?6
        WHERE id = ?1
        "#,
        params![
            key_id,
            next_attempts,
            status,
            locked_until,
            next_server_version(),
            utc_now_text()
        ],
    )?;
    get_client_secret_by_id(connection, key_id)?.ok_or_else(|| {
        PersistenceError::MissingRow("updated client secret failed attempts".to_string())
    })
}

pub fn reset_failed_attempts(connection: &Connection, key_id: i64) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE client_secrets
        SET failed_attempts = 0,
            locked_until = NULL,
            server_version = ?2,
            updated_at = ?3
        WHERE id = ?1
        "#,
        params![key_id, next_server_version(), utc_now_text()],
    )?;
    Ok(())
}

pub fn list_user_summary_rows(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<UserSummaryStatRow>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT s.id, s.lang, s.is_read, s.json_payload, r.normalized_url, r.created_at
        FROM summaries s
        JOIN requests r ON r.id = s.request_id
        WHERE r.user_id = ?1
          AND COALESCE(s.is_deleted, 0) = 0
        ORDER BY r.created_at DESC
        LIMIT 10000
        "#,
    )?;
    let rows = statement.query_map([user_id], |row| {
        Ok(UserSummaryStatRow {
            summary_id: row.get(0)?,
            lang: row.get(1)?,
            is_read: row.get(2)?,
            json_payload_raw: row.get(3)?,
            request_normalized_url: row.get(4)?,
            request_created_at: row.get(5)?,
        })
    })?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn allowlisted_table_counts(
    connection: &Connection,
) -> Result<Vec<(String, i64)>, PersistenceError> {
    let mut statement = connection.prepare(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )?;
    let rows = statement.query_map([], |row| row.get::<_, String>(0))?;
    let mut counts = Vec::new();
    for row in rows {
        let table = row?;
        if !DB_INFO_TABLE_ALLOWLIST.contains(&table.as_str()) {
            continue;
        }
        let query = format!("SELECT COUNT(*) FROM {table}");
        let count = connection.query_row(query.as_str(), [], |row| row.get::<_, i64>(0))?;
        counts.push((table, count));
    }
    Ok(counts)
}

fn get_refresh_token_by_id(
    connection: &Connection,
    token_id: i64,
) -> Result<Option<RefreshTokenRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, user_id, token_hash, client_id, device_info, ip_address, is_revoked,
               expires_at, last_used_at, created_at
        FROM refresh_tokens
        WHERE id = ?1
        "#,
    )?;
    statement
        .query_row([token_id], map_refresh_token_row)
        .optional()
        .map_err(PersistenceError::from)
}

fn map_user_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<UserRecord> {
    Ok(UserRecord {
        telegram_user_id: row.get(0)?,
        username: row.get(1)?,
        is_owner: row.get(2)?,
        preferences_json: parse_json_opt(row.get::<_, Option<String>>(3)?).map_err(to_sql_err)?,
        linked_telegram_user_id: row.get(4)?,
        linked_telegram_username: row.get(5)?,
        linked_telegram_photo_url: row.get(6)?,
        linked_telegram_first_name: row.get(7)?,
        linked_telegram_last_name: row.get(8)?,
        linked_at: row.get(9)?,
        link_nonce: row.get(10)?,
        link_nonce_expires_at: row.get(11)?,
        created_at: row.get(12)?,
        updated_at: row.get(13)?,
    })
}

fn map_refresh_token_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<RefreshTokenRecord> {
    Ok(RefreshTokenRecord {
        id: row.get(0)?,
        user_id: row.get(1)?,
        token_hash: row.get(2)?,
        client_id: row.get(3)?,
        device_info: row.get(4)?,
        ip_address: row.get(5)?,
        is_revoked: row.get(6)?,
        expires_at: row.get(7)?,
        last_used_at: row.get(8)?,
        created_at: row.get(9)?,
    })
}

fn map_client_secret_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<ClientSecretRecord> {
    Ok(ClientSecretRecord {
        id: row.get(0)?,
        user_id: row.get(1)?,
        client_id: row.get(2)?,
        secret_hash: row.get(3)?,
        secret_salt: row.get(4)?,
        status: row.get(5)?,
        label: row.get(6)?,
        description: row.get(7)?,
        expires_at: row.get(8)?,
        last_used_at: row.get(9)?,
        failed_attempts: row.get(10)?,
        locked_until: row.get(11)?,
        created_at: row.get(12)?,
        updated_at: row.get(13)?,
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

fn utc_now_text() -> String {
    Utc::now().to_rfc3339()
}

fn next_server_version() -> i64 {
    Utc::now().timestamp_millis()
}

pub fn normalize_datetime_text(value: Option<&str>) -> Option<String> {
    let Some(raw) = value else {
        return None;
    };
    if raw.trim().is_empty() {
        return None;
    }

    if let Ok(parsed) = DateTime::parse_from_rfc3339(raw) {
        return Some(
            parsed
                .with_timezone(&Utc)
                .to_rfc3339()
                .replace("+00:00", "Z"),
        );
    }
    if let Ok(parsed) = chrono::NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S%.f") {
        return Some(
            DateTime::<Utc>::from_naive_utc_and_offset(parsed, Utc)
                .to_rfc3339()
                .replace("+00:00", "Z"),
        );
    }
    if let Ok(parsed) = chrono::NaiveDateTime::parse_from_str(raw, "%Y-%m-%d %H:%M:%S") {
        return Some(
            DateTime::<Utc>::from_naive_utc_and_offset(parsed, Utc)
                .to_rfc3339()
                .replace("+00:00", "Z"),
        );
    }

    Some(if raw.ends_with('Z') {
        raw.to_string()
    } else {
        format!("{raw}Z")
    })
}
