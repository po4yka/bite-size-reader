use std::cmp::Ordering;

use chrono::{DateTime, Utc};
use rand::RngCore;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::PersistenceError;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CollectionRecord {
    pub id: i64,
    pub user_id: i64,
    pub name: String,
    pub description: Option<String>,
    pub parent_id: Option<i64>,
    pub position: Option<i64>,
    pub server_version: Option<i64>,
    pub updated_at: Option<String>,
    pub created_at: Option<String>,
    pub is_shared: bool,
    pub share_count: i64,
    pub is_deleted: bool,
    pub deleted_at: Option<String>,
    pub item_count: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CollectionItemRecord {
    pub collection_id: i64,
    pub summary_id: i64,
    pub position: Option<i64>,
    pub created_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CollectionAclRecord {
    pub user_id: Option<i64>,
    pub role: String,
    pub status: String,
    pub invited_by: Option<i64>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CollectionInviteRecord {
    pub id: i64,
    pub collection_id: i64,
    pub token: String,
    pub role: String,
    pub expires_at: Option<String>,
    pub used_at: Option<String>,
    pub status: String,
    pub server_version: Option<i64>,
    pub created_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MoveCollectionRecord {
    pub id: i64,
    pub parent_id: Option<i64>,
    pub position: i64,
    pub server_version: Option<i64>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MoveItemsResult {
    pub moved_summary_ids: Vec<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SyncEntityRecord {
    pub entity_type: String,
    pub id: Value,
    pub server_version: i64,
    pub updated_at: String,
    pub deleted_at: Option<String>,
    pub summary: Option<Value>,
    pub request: Option<Value>,
    pub preference: Option<Value>,
    pub stat: Option<Value>,
    pub crawl_result: Option<Value>,
    pub llm_call: Option<Value>,
}

pub fn get_collection_by_id(
    connection: &Connection,
    collection_id: i64,
    include_deleted: bool,
) -> Result<Option<CollectionRecord>, PersistenceError> {
    let sql = if include_deleted {
        r#"
        SELECT collections.id,
               collections.user_id,
               collections.name,
               collections.description,
               collections.parent_id,
               collections.position,
               collections.server_version,
               collections.updated_at,
               collections.created_at,
               collections.is_shared,
               collections.share_count,
               collections.is_deleted,
               collections.deleted_at,
               (
                   SELECT COUNT(*)
                   FROM collection_items
                   WHERE collection_items.collection_id = collections.id
               ) AS item_count
        FROM collections
        WHERE collections.id = ?1
        "#
    } else {
        r#"
        SELECT collections.id,
               collections.user_id,
               collections.name,
               collections.description,
               collections.parent_id,
               collections.position,
               collections.server_version,
               collections.updated_at,
               collections.created_at,
               collections.is_shared,
               collections.share_count,
               collections.is_deleted,
               collections.deleted_at,
               (
                   SELECT COUNT(*)
                   FROM collection_items
                   WHERE collection_items.collection_id = collections.id
               ) AS item_count
        FROM collections
        WHERE collections.id = ?1
          AND collections.is_deleted = 0
        "#
    };

    connection
        .query_row(sql, [collection_id], map_collection_row)
        .optional()
        .map_err(PersistenceError::from)
}

pub fn list_collections_for_user(
    connection: &Connection,
    user_id: i64,
    parent_id: Option<i64>,
    limit: i64,
    offset: i64,
) -> Result<Vec<CollectionRecord>, PersistenceError> {
    let sql = if parent_id.is_some() {
        r#"
        SELECT collections.id,
               collections.user_id,
               collections.name,
               collections.description,
               collections.parent_id,
               collections.position,
               collections.server_version,
               collections.updated_at,
               collections.created_at,
               collections.is_shared,
               collections.share_count,
               collections.is_deleted,
               collections.deleted_at,
               (
                   SELECT COUNT(*)
                   FROM collection_items
                   WHERE collection_items.collection_id = collections.id
               ) AS item_count
        FROM collections
        WHERE collections.user_id = ?1
          AND collections.parent_id = ?2
          AND collections.is_deleted = 0
        ORDER BY collections.position, collections.created_at
        LIMIT ?3 OFFSET ?4
        "#
    } else {
        r#"
        SELECT collections.id,
               collections.user_id,
               collections.name,
               collections.description,
               collections.parent_id,
               collections.position,
               collections.server_version,
               collections.updated_at,
               collections.created_at,
               collections.is_shared,
               collections.share_count,
               collections.is_deleted,
               collections.deleted_at,
               (
                   SELECT COUNT(*)
                   FROM collection_items
                   WHERE collection_items.collection_id = collections.id
               ) AS item_count
        FROM collections
        WHERE collections.user_id = ?1
          AND collections.parent_id IS NULL
          AND collections.is_deleted = 0
        ORDER BY collections.position, collections.created_at
        LIMIT ?2 OFFSET ?3
        "#
    };

    let mut statement = connection.prepare(sql)?;
    let rows = if let Some(parent_id) = parent_id {
        statement.query_map(params![user_id, parent_id, limit.max(0), offset.max(0)], map_collection_row)?
    } else {
        statement.query_map(params![user_id, limit.max(0), offset.max(0)], map_collection_row)?
    };

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn list_collection_tree(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<CollectionRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT DISTINCT collections.id,
               collections.user_id,
               collections.name,
               collections.description,
               collections.parent_id,
               collections.position,
               collections.server_version,
               collections.updated_at,
               collections.created_at,
               collections.is_shared,
               collections.share_count,
               collections.is_deleted,
               collections.deleted_at,
               (
                   SELECT COUNT(*)
                   FROM collection_items
                   WHERE collection_items.collection_id = collections.id
               ) AS item_count
        FROM collections
        LEFT JOIN collection_collaborators
          ON collection_collaborators.collection_id = collections.id
         AND collection_collaborators.user_id = ?1
         AND collection_collaborators.status = 'active'
        WHERE collections.is_deleted = 0
          AND (
                collections.user_id = ?1
             OR collection_collaborators.collection_id IS NOT NULL
          )
        ORDER BY collections.parent_id, collections.position, collections.created_at
        "#,
    )?;

    let rows = statement.query_map([user_id], map_collection_row)?;
    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn get_collection_role(
    connection: &Connection,
    collection_id: i64,
    user_id: i64,
) -> Result<Option<String>, PersistenceError> {
    let owner_id = connection
        .query_row(
            r#"
            SELECT user_id
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;

    let Some(owner_id) = owner_id else {
        return Ok(None);
    };
    if owner_id == user_id {
        return Ok(Some("owner".to_string()));
    }

    connection
        .query_row(
            r#"
            SELECT role
            FROM collection_collaborators
            WHERE collection_id = ?1
              AND user_id = ?2
              AND status = 'active'
            "#,
            params![collection_id, user_id],
            |row| row.get::<_, String>(0),
        )
        .optional()
        .map_err(PersistenceError::from)
}

pub fn get_next_collection_position(
    connection: &Connection,
    parent_id: Option<i64>,
) -> Result<i64, PersistenceError> {
    let max_position = if let Some(parent_id) = parent_id {
        connection.query_row(
            r#"
            SELECT MAX(position)
            FROM collections
            WHERE parent_id = ?1
              AND is_deleted = 0
            "#,
            [parent_id],
            |row| row.get::<_, Option<i64>>(0),
        )?
    } else {
        connection.query_row(
            r#"
            SELECT MAX(position)
            FROM collections
            WHERE parent_id IS NULL
              AND is_deleted = 0
            "#,
            [],
            |row| row.get::<_, Option<i64>>(0),
        )?
    };
    Ok(max_position.unwrap_or(0) + 1)
}

pub fn shift_collection_positions(
    connection: &Connection,
    parent_id: Option<i64>,
    start: i64,
) -> Result<(), PersistenceError> {
    if let Some(parent_id) = parent_id {
        connection.execute(
            r#"
            UPDATE collections
            SET position = position + 1
            WHERE parent_id = ?1
              AND position IS NOT NULL
              AND position >= ?2
            "#,
            params![parent_id, start],
        )?;
    } else {
        connection.execute(
            r#"
            UPDATE collections
            SET position = position + 1
            WHERE parent_id IS NULL
              AND position IS NOT NULL
              AND position >= ?1
            "#,
            [start],
        )?;
    }
    Ok(())
}

pub fn create_collection(
    connection: &Connection,
    user_id: i64,
    name: &str,
    description: Option<&str>,
    parent_id: Option<i64>,
    position: i64,
) -> Result<i64, PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        INSERT INTO collections (
            user_id, name, description, parent_id, position, server_version,
            updated_at, created_at, is_shared, share_count, is_deleted, deleted_at
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?7, 0, 0, 0, NULL)
        "#,
        params![
            user_id,
            name,
            description,
            parent_id,
            position,
            next_server_version(),
            now
        ],
    )?;
    Ok(connection.last_insert_rowid())
}

pub fn update_collection(
    connection: &Connection,
    collection_id: i64,
    name: Option<&str>,
    description: Option<&str>,
    parent_id: Option<i64>,
    position: Option<i64>,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE collections
        SET name = COALESCE(?2, name),
            description = COALESCE(?3, description),
            parent_id = COALESCE(?4, parent_id),
            position = COALESCE(?5, position),
            server_version = ?6,
            updated_at = ?7
        WHERE id = ?1
          AND is_deleted = 0
        "#,
        params![
            collection_id,
            name,
            description,
            parent_id,
            position,
            next_server_version(),
            now
        ],
    )?;
    Ok(())
}

pub fn touch_collection(
    connection: &Connection,
    collection_id: i64,
) -> Result<(), PersistenceError> {
    connection.execute(
        r#"
        UPDATE collections
        SET updated_at = ?2,
            server_version = ?3
        WHERE id = ?1
        "#,
        params![collection_id, utc_now_text(), next_server_version()],
    )?;
    Ok(())
}

pub fn soft_delete_collection(
    connection: &Connection,
    collection_id: i64,
) -> Result<(), PersistenceError> {
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE collections
        SET is_deleted = 1,
            deleted_at = ?2,
            server_version = ?3,
            updated_at = ?2
        WHERE id = ?1
          AND is_deleted = 0
        "#,
        params![collection_id, now, next_server_version()],
    )?;
    Ok(())
}

pub fn list_collection_items(
    connection: &Connection,
    collection_id: i64,
    limit: i64,
    offset: i64,
) -> Result<Vec<CollectionItemRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT collection_id, summary_id, position, created_at
        FROM collection_items
        WHERE collection_id = ?1
        ORDER BY position, created_at
        LIMIT ?2 OFFSET ?3
        "#,
    )?;
    let rows = statement.query_map(params![collection_id, limit.max(0), offset.max(0)], |row| {
        Ok(CollectionItemRecord {
            collection_id: row.get(0)?,
            summary_id: row.get(1)?,
            position: row.get(2)?,
            created_at: row.get(3)?,
        })
    })?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn get_next_collection_item_position(
    connection: &Connection,
    collection_id: i64,
) -> Result<i64, PersistenceError> {
    let max_position = connection.query_row(
        r#"
        SELECT MAX(position)
        FROM collection_items
        WHERE collection_id = ?1
        "#,
        [collection_id],
        |row| row.get::<_, Option<i64>>(0),
    )?;
    Ok(max_position.unwrap_or(0) + 1)
}

pub fn add_collection_item(
    connection: &Connection,
    collection_id: i64,
    summary_id: i64,
    position: i64,
) -> Result<bool, PersistenceError> {
    let collection_exists = connection
        .query_row(
            r#"
            SELECT 1
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !collection_exists {
        return Ok(false);
    }

    let summary_exists = connection
        .query_row("SELECT 1 FROM summaries WHERE id = ?1", [summary_id], |_| Ok(()))
        .optional()?
        .is_some();
    if !summary_exists {
        return Ok(false);
    }

    let inserted = connection.execute(
        r#"
        INSERT OR IGNORE INTO collection_items (
            collection_id, summary_id, position, created_at
        ) VALUES (?1, ?2, ?3, ?4)
        "#,
        params![collection_id, summary_id, position, utc_now_text()],
    )?;
    if inserted == 0 {
        return Ok(false);
    }
    touch_collection(connection, collection_id)?;
    Ok(true)
}

pub fn remove_collection_item(
    connection: &Connection,
    collection_id: i64,
    summary_id: i64,
) -> Result<(), PersistenceError> {
    let collection_exists = connection
        .query_row(
            r#"
            SELECT 1
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !collection_exists {
        return Ok(());
    }

    connection.execute(
        r#"
        DELETE FROM collection_items
        WHERE collection_id = ?1
          AND summary_id = ?2
        "#,
        params![collection_id, summary_id],
    )?;
    touch_collection(connection, collection_id)?;
    Ok(())
}

pub fn reorder_collection_items(
    connection: &Connection,
    collection_id: i64,
    item_positions: &[(i64, i64)],
) -> Result<(), PersistenceError> {
    let collection_exists = connection
        .query_row(
            r#"
            SELECT 1
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !collection_exists {
        return Ok(());
    }

    for (summary_id, position) in item_positions {
        connection.execute(
            r#"
            UPDATE collection_items
            SET position = ?3
            WHERE collection_id = ?1
              AND summary_id = ?2
            "#,
            params![collection_id, summary_id, position],
        )?;
    }
    touch_collection(connection, collection_id)?;
    Ok(())
}

pub fn move_collection_items(
    connection: &Connection,
    source_collection_id: i64,
    target_collection_id: i64,
    summary_ids: &[i64],
    position: Option<i64>,
) -> Result<MoveItemsResult, PersistenceError> {
    let source_exists = connection
        .query_row(
            r#"
            SELECT 1 FROM collections
            WHERE id = ?1 AND is_deleted = 0
            "#,
            [source_collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    let target_exists = connection
        .query_row(
            r#"
            SELECT 1 FROM collections
            WHERE id = ?1 AND is_deleted = 0
            "#,
            [target_collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !source_exists || !target_exists {
        return Ok(MoveItemsResult {
            moved_summary_ids: Vec::new(),
        });
    }

    let mut insert_pos = match position {
        Some(value) => value,
        None => get_next_collection_item_position(connection, target_collection_id)?,
    };

    let mut moved_summary_ids = Vec::new();
    for summary_id in summary_ids {
        connection.execute(
            r#"
            DELETE FROM collection_items
            WHERE collection_id = ?1
              AND summary_id = ?2
            "#,
            params![source_collection_id, summary_id],
        )?;

        if position.is_some() {
            connection.execute(
                r#"
                UPDATE collection_items
                SET position = position + 1
                WHERE collection_id = ?1
                  AND position IS NOT NULL
                  AND position >= ?2
                "#,
                params![target_collection_id, insert_pos],
            )?;
        }

        let inserted = connection.execute(
            r#"
            INSERT OR IGNORE INTO collection_items (
                collection_id, summary_id, position, created_at
            ) VALUES (?1, ?2, ?3, ?4)
            "#,
            params![target_collection_id, summary_id, insert_pos, utc_now_text()],
        )?;
        if inserted > 0 {
            moved_summary_ids.push(*summary_id);
            insert_pos += 1;
        }
    }

    touch_collection(connection, source_collection_id)?;
    touch_collection(connection, target_collection_id)?;
    Ok(MoveItemsResult { moved_summary_ids })
}

pub fn reorder_collections(
    connection: &Connection,
    parent_id: Option<i64>,
    item_positions: &[(i64, i64)],
) -> Result<(), PersistenceError> {
    for (collection_id, position) in item_positions {
        let matched = if let Some(parent_id) = parent_id {
            connection.execute(
                r#"
                UPDATE collections
                SET position = ?3
                WHERE id = ?1
                  AND parent_id = ?2
                  AND is_deleted = 0
                "#,
                params![collection_id, parent_id, position],
            )?
        } else {
            connection.execute(
                r#"
                UPDATE collections
                SET position = ?2
                WHERE id = ?1
                  AND parent_id IS NULL
                  AND is_deleted = 0
                "#,
                params![collection_id, position],
            )?
        };
        if matched == 0 {
            continue;
        }
    }
    Ok(())
}

pub fn move_collection(
    connection: &Connection,
    collection_id: i64,
    parent_id: Option<i64>,
    position: i64,
) -> Result<Option<MoveCollectionRecord>, PersistenceError> {
    let collection = get_collection_by_id(connection, collection_id, false)?;
    let Some(_collection) = collection else {
        return Ok(None);
    };

    if let Some(parent_id) = parent_id {
        let mut ancestor_id = Some(parent_id);
        while let Some(current_id) = ancestor_id {
            if current_id == collection_id {
                return Ok(None);
            }
            ancestor_id = connection
                .query_row(
                    r#"
                    SELECT parent_id
                    FROM collections
                    WHERE id = ?1
                      AND is_deleted = 0
                    "#,
                    [current_id],
                    |row| row.get::<_, Option<i64>>(0),
                )
                .optional()?
                .flatten();
        }
    }

    shift_collection_positions(connection, parent_id, position)?;
    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE collections
        SET parent_id = ?2,
            position = ?3,
            server_version = ?4,
            updated_at = ?5
        WHERE id = ?1
        "#,
        params![collection_id, parent_id, position, next_server_version(), now],
    )?;

    Ok(get_collection_by_id(connection, collection_id, false)?.map(|record| MoveCollectionRecord {
        id: record.id,
        parent_id: record.parent_id,
        position: record.position.unwrap_or(position),
        server_version: record.server_version,
        updated_at: record.updated_at,
    }))
}

pub fn get_collection_owner_info(
    connection: &Connection,
    collection_id: i64,
) -> Result<Option<CollectionAclRecord>, PersistenceError> {
    connection
        .query_row(
            r#"
            SELECT user_id
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |row| {
                Ok(CollectionAclRecord {
                    user_id: Some(row.get(0)?),
                    role: "owner".to_string(),
                    status: "active".to_string(),
                    invited_by: None,
                    created_at: None,
                    updated_at: None,
                })
            },
        )
        .optional()
        .map_err(PersistenceError::from)
}

pub fn list_collection_collaborators(
    connection: &Connection,
    collection_id: i64,
) -> Result<Vec<CollectionAclRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT user_id, role, status, invited_by_id, created_at, updated_at
        FROM collection_collaborators
        WHERE collection_id = ?1
        ORDER BY created_at
        "#,
    )?;
    let rows = statement.query_map([collection_id], |row| {
        Ok(CollectionAclRecord {
            user_id: row.get(0)?,
            role: row.get(1)?,
            status: row.get(2)?,
            invited_by: row.get(3)?,
            created_at: row.get(4)?,
            updated_at: row.get(5)?,
        })
    })?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

pub fn add_collection_collaborator(
    connection: &Connection,
    collection_id: i64,
    target_user_id: i64,
    role: &str,
    invited_by: Option<i64>,
) -> Result<(), PersistenceError> {
    let owner_id = connection
        .query_row(
            r#"
            SELECT user_id
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    let Some(owner_id) = owner_id else {
        return Ok(());
    };
    if owner_id == target_user_id {
        return Ok(());
    }

    let now = utc_now_text();
    connection.execute(
        r#"
        INSERT INTO collection_collaborators (
            collection_id, user_id, role, status, invited_by_id, server_version, created_at, updated_at
        ) VALUES (?1, ?2, ?3, 'active', ?4, ?5, ?6, ?6)
        ON CONFLICT(collection_id, user_id) DO UPDATE
        SET role = excluded.role,
            status = 'active',
            invited_by_id = excluded.invited_by_id,
            server_version = excluded.server_version,
            updated_at = excluded.updated_at
        "#,
        params![
            collection_id,
            target_user_id,
            role,
            invited_by,
            next_server_version(),
            now
        ],
    )?;
    refresh_collection_share_state(connection, collection_id)?;
    Ok(())
}

pub fn remove_collection_collaborator(
    connection: &Connection,
    collection_id: i64,
    target_user_id: i64,
) -> Result<(), PersistenceError> {
    let owner_id = connection
        .query_row(
            r#"
            SELECT user_id
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    let Some(owner_id) = owner_id else {
        return Ok(());
    };
    if owner_id == target_user_id {
        return Ok(());
    }

    connection.execute(
        r#"
        DELETE FROM collection_collaborators
        WHERE collection_id = ?1
          AND user_id = ?2
        "#,
        params![collection_id, target_user_id],
    )?;
    refresh_collection_share_state(connection, collection_id)?;
    Ok(())
}

pub fn create_collection_invite(
    connection: &Connection,
    collection_id: i64,
    role: &str,
    expires_at: Option<&str>,
) -> Result<Option<CollectionInviteRecord>, PersistenceError> {
    let exists = connection
        .query_row(
            r#"
            SELECT 1
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [collection_id],
            |_| Ok(()),
        )
        .optional()?
        .is_some();
    if !exists {
        return Ok(None);
    }

    let token = random_hex_token();
    let now = utc_now_text();
    let server_version = next_server_version();
    connection.execute(
        r#"
        INSERT INTO collection_invites (
            collection_id, token, role, expires_at, used_at, status, server_version, created_at, updated_at
        ) VALUES (?1, ?2, ?3, ?4, NULL, 'active', ?5, ?6, ?6)
        "#,
        params![collection_id, token, role, expires_at, server_version, now],
    )?;
    let invite_id = connection.last_insert_rowid();
    get_collection_invite_by_id(connection, invite_id)
}

pub fn accept_collection_invite(
    connection: &Connection,
    token: &str,
    user_id: i64,
) -> Result<Option<Value>, PersistenceError> {
    let invite = get_collection_invite_by_token(connection, token)?;
    let Some(invite) = invite else {
        return Ok(None);
    };
    if matches!(invite.status.as_str(), "used" | "revoked") {
        return Ok(None);
    }
    if invite
        .expires_at
        .as_deref()
        .and_then(parse_datetime_utc)
        .is_some_and(|expires_at| expires_at < Utc::now())
    {
        connection.execute(
            r#"
            UPDATE collection_invites
            SET status = 'expired',
                server_version = ?2,
                updated_at = ?3
            WHERE id = ?1
            "#,
            params![invite.id, next_server_version(), utc_now_text()],
        )?;
        return Ok(None);
    }

    let collection_owner_id = connection
        .query_row(
            r#"
            SELECT user_id
            FROM collections
            WHERE id = ?1
              AND is_deleted = 0
            "#,
            [invite.collection_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?;
    let Some(collection_owner_id) = collection_owner_id else {
        return Ok(None);
    };

    if user_id != collection_owner_id {
        add_collection_collaborator(
            connection,
            invite.collection_id,
            user_id,
            &invite.role,
            Some(collection_owner_id),
        )?;
    }

    let now = utc_now_text();
    connection.execute(
        r#"
        UPDATE collection_invites
        SET used_at = ?2,
            status = 'used',
            server_version = ?3,
            updated_at = ?2
        WHERE id = ?1
        "#,
        params![invite.id, now, next_server_version()],
    )?;

    Ok(Some(json!({
        "collection_id": invite.collection_id,
        "role": invite.role,
        "status": "accepted",
    })))
}

pub fn list_sync_entities_for_user(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<SyncEntityRecord>, PersistenceError> {
    let mut records = Vec::new();

    if let Some(user_record) = connection
        .query_row(
            r#"
            SELECT telegram_user_id, username, is_owner, preferences_json, created_at, updated_at, server_version
            FROM users
            WHERE telegram_user_id = ?1
            "#,
            [user_id],
            |row| {
                Ok(SyncEntityRecord {
                    entity_type: "user".to_string(),
                    id: json!(row.get::<_, i64>(0)?),
                    server_version: row.get::<_, Option<i64>>(6)?.unwrap_or_default(),
                    updated_at: python_like_iso_text(row.get::<_, Option<String>>(5)?.as_deref()),
                    deleted_at: None,
                    summary: None,
                    request: None,
                    preference: Some(json!({
                        "username": row.get::<_, Option<String>>(1)?,
                        "is_owner": int_to_bool(row.get::<_, Option<i64>>(2)?),
                        "preferences": parse_optional_json_text(
                            row.get::<_, Option<String>>(3)?.as_deref(),
                        )
                        .map_err(to_sql_error)?,
                        "created_at": python_like_iso_text(row.get::<_, Option<String>>(4)?.as_deref()),
                    })),
                    stat: None,
                    crawl_result: None,
                    llm_call: None,
                })
            },
        )
        .optional()?
    {
        records.push(user_record);
    }

    records.extend(list_request_sync_entities(connection, user_id)?);
    records.extend(list_summary_sync_entities(connection, user_id)?);
    records.extend(list_crawl_sync_entities(connection, user_id)?);
    records.extend(list_llm_sync_entities(connection, user_id)?);
    records.sort_by(sync_entity_ordering);
    Ok(records)
}

pub fn get_summary_sync_entity_for_user(
    connection: &Connection,
    summary_id: i64,
    user_id: i64,
) -> Result<Option<SyncEntityRecord>, PersistenceError> {
    connection
        .query_row(
            r#"
            SELECT summaries.id,
                   summaries.server_version,
                   summaries.updated_at,
                   summaries.deleted_at,
                   summaries.is_deleted,
                   summaries.request_id,
                   summaries.lang,
                   summaries.is_read,
                   summaries.json_payload,
                   summaries.created_at
            FROM summaries
            JOIN requests ON requests.id = summaries.request_id
            WHERE summaries.id = ?1
              AND requests.user_id = ?2
            "#,
            params![summary_id, user_id],
            map_summary_sync_row,
        )
        .optional()
        .map_err(PersistenceError::from)
}

pub fn apply_summary_sync_change(
    connection: &Connection,
    summary_id: i64,
    is_deleted: Option<bool>,
    deleted_at: Option<&str>,
    is_read: Option<bool>,
) -> Result<i64, PersistenceError> {
    connection.execute(
        r#"
        UPDATE summaries
        SET is_deleted = COALESCE(?2, is_deleted),
            deleted_at = COALESCE(?3, deleted_at),
            is_read = COALESCE(?4, is_read)
        WHERE id = ?1
        "#,
        params![
            summary_id,
            is_deleted.map(bool_to_int),
            deleted_at,
            is_read.map(bool_to_int)
        ],
    )?;

    Ok(connection
        .query_row(
            "SELECT COALESCE(server_version, 0) FROM summaries WHERE id = ?1",
            [summary_id],
            |row| row.get::<_, i64>(0),
        )
        .optional()?
        .unwrap_or_default())
}

fn list_request_sync_entities(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<SyncEntityRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT id, type, status, input_url, normalized_url, correlation_id, created_at,
               server_version, updated_at, deleted_at, is_deleted
        FROM requests
        WHERE user_id = ?1
        "#,
    )?;
    let rows = statement.query_map([user_id], |row| {
        let id = row.get::<_, i64>(0)?;
        let is_deleted = int_to_bool(row.get::<_, Option<i64>>(10)?);
        let deleted_at = row.get::<_, Option<String>>(9)?;
        Ok(SyncEntityRecord {
            entity_type: "request".to_string(),
            id: json!(id),
            server_version: row.get::<_, Option<i64>>(7)?.unwrap_or_default(),
            updated_at: python_like_iso_text(row.get::<_, Option<String>>(8)?.as_deref()),
            deleted_at: deleted_at.as_deref().map(python_like_iso_text_if_present),
            summary: None,
            request: if is_deleted {
                None
            } else {
                Some(json!({
                    "id": id,
                    "type": row.get::<_, Option<String>>(1)?,
                    "status": row.get::<_, Option<String>>(2)?,
                    "input_url": row.get::<_, Option<String>>(3)?,
                    "normalized_url": row.get::<_, Option<String>>(4)?,
                    "correlation_id": row.get::<_, Option<String>>(5)?,
                    "created_at": python_like_iso_text(row.get::<_, Option<String>>(6)?.as_deref()),
                }))
            },
            preference: None,
            stat: None,
            crawl_result: None,
            llm_call: None,
        })
    })?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

fn list_summary_sync_entities(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<SyncEntityRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT summaries.id,
               summaries.server_version,
               summaries.updated_at,
               summaries.deleted_at,
               summaries.is_deleted,
               summaries.request_id,
               summaries.lang,
               summaries.is_read,
               summaries.json_payload,
               summaries.created_at
        FROM summaries
        JOIN requests ON requests.id = summaries.request_id
        WHERE requests.user_id = ?1
        "#,
    )?;
    let rows = statement.query_map([user_id], map_summary_sync_row)?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

fn list_crawl_sync_entities(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<SyncEntityRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT crawl_results.id,
               crawl_results.server_version,
               crawl_results.updated_at,
               crawl_results.deleted_at,
               crawl_results.is_deleted,
               crawl_results.request_id,
               crawl_results.source_url,
               crawl_results.endpoint,
               crawl_results.http_status,
               crawl_results.metadata_json,
               crawl_results.latency_ms
        FROM crawl_results
        JOIN requests ON requests.id = crawl_results.request_id
        WHERE requests.user_id = ?1
        "#,
    )?;
    let rows = statement.query_map([user_id], |row| {
        let is_deleted = int_to_bool(row.get::<_, Option<i64>>(4)?);
        let deleted_at = row.get::<_, Option<String>>(3)?;
        Ok(SyncEntityRecord {
            entity_type: "crawl_result".to_string(),
            id: json!(row.get::<_, i64>(0)?),
            server_version: row.get::<_, Option<i64>>(1)?.unwrap_or_default(),
            updated_at: python_like_iso_text(row.get::<_, Option<String>>(2)?.as_deref()),
            deleted_at: deleted_at.as_deref().map(python_like_iso_text_if_present),
            summary: None,
            request: None,
            preference: None,
            stat: None,
            crawl_result: if is_deleted {
                None
            } else {
                Some(json!({
                    "request_id": row.get::<_, i64>(5)?,
                    "source_url": row.get::<_, Option<String>>(6)?,
                    "endpoint": row.get::<_, Option<String>>(7)?,
                    "http_status": row.get::<_, Option<i64>>(8)?,
                    "metadata": parse_optional_json_text(
                        row.get::<_, Option<String>>(9)?.as_deref(),
                    )
                    .map_err(to_sql_error)?,
                    "latency_ms": row.get::<_, Option<i64>>(10)?,
                }))
            },
            llm_call: None,
        })
    })?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

fn list_llm_sync_entities(
    connection: &Connection,
    user_id: i64,
) -> Result<Vec<SyncEntityRecord>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT llm_calls.id,
               llm_calls.server_version,
               llm_calls.updated_at,
               llm_calls.deleted_at,
               llm_calls.is_deleted,
               llm_calls.request_id,
               llm_calls.provider,
               llm_calls.model,
               llm_calls.status,
               llm_calls.tokens_prompt,
               llm_calls.tokens_completion,
               llm_calls.cost_usd,
               llm_calls.created_at
        FROM llm_calls
        JOIN requests ON requests.id = llm_calls.request_id
        WHERE requests.user_id = ?1
        "#,
    )?;
    let rows = statement.query_map([user_id], |row| {
        let is_deleted = int_to_bool(row.get::<_, Option<i64>>(4)?);
        let deleted_at = row.get::<_, Option<String>>(3)?;
        Ok(SyncEntityRecord {
            entity_type: "llm_call".to_string(),
            id: json!(row.get::<_, i64>(0)?),
            server_version: row.get::<_, Option<i64>>(1)?.unwrap_or_default(),
            updated_at: python_like_iso_text(row.get::<_, Option<String>>(2)?.as_deref()),
            deleted_at: deleted_at.as_deref().map(python_like_iso_text_if_present),
            summary: None,
            request: None,
            preference: None,
            stat: None,
            crawl_result: None,
            llm_call: if is_deleted {
                None
            } else {
                Some(json!({
                    "request_id": row.get::<_, i64>(5)?,
                    "provider": row.get::<_, Option<String>>(6)?,
                    "model": row.get::<_, Option<String>>(7)?,
                    "status": row.get::<_, Option<String>>(8)?,
                    "tokens_prompt": row.get::<_, Option<i64>>(9)?,
                    "tokens_completion": row.get::<_, Option<i64>>(10)?,
                    "cost_usd": row.get::<_, Option<f64>>(11)?,
                    "created_at": python_like_iso_text(row.get::<_, Option<String>>(12)?.as_deref()),
                }))
            },
        })
    })?;

    let mut records = Vec::new();
    for row in rows {
        records.push(row?);
    }
    Ok(records)
}

fn map_summary_sync_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<SyncEntityRecord> {
    let id = row.get::<_, i64>(0)?;
    let server_version = row.get::<_, Option<i64>>(1)?.unwrap_or_default();
    let updated_at = python_like_iso_text(row.get::<_, Option<String>>(2)?.as_deref());
    let deleted_at = row
        .get::<_, Option<String>>(3)?
        .as_deref()
        .map(python_like_iso_text_if_present);
    let is_deleted = int_to_bool(row.get::<_, Option<i64>>(4)?);
    let request_id = row.get::<_, i64>(5)?;
    let lang = row.get::<_, Option<String>>(6)?;
    let is_read = int_to_bool(row.get::<_, Option<i64>>(7)?);
    let json_payload = parse_optional_json_text(row.get::<_, Option<String>>(8)?.as_deref())
        .map_err(to_sql_error)?;
    let created_at = python_like_iso_text(row.get::<_, Option<String>>(9)?.as_deref());

    Ok(SyncEntityRecord {
        entity_type: "summary".to_string(),
        id: json!(id),
        server_version,
        updated_at,
        deleted_at,
        summary: if is_deleted {
            None
        } else {
            Some(json!({
                "id": id,
                "request_id": request_id,
                "lang": lang,
                "is_read": is_read,
                "json_payload": json_payload,
                "created_at": created_at,
            }))
        },
        request: None,
        preference: None,
        stat: None,
        crawl_result: None,
        llm_call: None,
    })
}

fn refresh_collection_share_state(
    connection: &Connection,
    collection_id: i64,
) -> Result<(), PersistenceError> {
    let share_count = connection.query_row(
        r#"
        SELECT COUNT(*)
        FROM collection_collaborators
        WHERE collection_id = ?1
          AND status = 'active'
        "#,
        [collection_id],
        |row| row.get::<_, i64>(0),
    )?;
    connection.execute(
        r#"
        UPDATE collections
        SET is_shared = ?2,
            share_count = ?3,
            updated_at = ?4,
            server_version = ?5
        WHERE id = ?1
        "#,
        params![
            collection_id,
            bool_to_int(share_count > 0),
            share_count,
            utc_now_text(),
            next_server_version()
        ],
    )?;
    Ok(())
}

fn get_collection_invite_by_id(
    connection: &Connection,
    invite_id: i64,
) -> Result<Option<CollectionInviteRecord>, PersistenceError> {
    connection
        .query_row(
            r#"
            SELECT id, collection_id, token, role, expires_at, used_at, status,
                   server_version, created_at, updated_at
            FROM collection_invites
            WHERE id = ?1
            "#,
            [invite_id],
            map_collection_invite_row,
        )
        .optional()
        .map_err(PersistenceError::from)
}

fn get_collection_invite_by_token(
    connection: &Connection,
    token: &str,
) -> Result<Option<CollectionInviteRecord>, PersistenceError> {
    connection
        .query_row(
            r#"
            SELECT id, collection_id, token, role, expires_at, used_at, status,
                   server_version, created_at, updated_at
            FROM collection_invites
            WHERE token = ?1
            "#,
            [token],
            map_collection_invite_row,
        )
        .optional()
        .map_err(PersistenceError::from)
}

fn map_collection_invite_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<CollectionInviteRecord> {
    Ok(CollectionInviteRecord {
        id: row.get(0)?,
        collection_id: row.get(1)?,
        token: row.get(2)?,
        role: row.get(3)?,
        expires_at: row.get(4)?,
        used_at: row.get(5)?,
        status: row.get(6)?,
        server_version: row.get(7)?,
        created_at: row.get(8)?,
        updated_at: row.get(9)?,
    })
}

fn map_collection_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<CollectionRecord> {
    Ok(CollectionRecord {
        id: row.get(0)?,
        user_id: row.get(1)?,
        name: row.get(2)?,
        description: row.get(3)?,
        parent_id: row.get(4)?,
        position: row.get(5)?,
        server_version: row.get(6)?,
        updated_at: row.get(7)?,
        created_at: row.get(8)?,
        is_shared: int_to_bool(row.get::<_, Option<i64>>(9)?),
        share_count: row.get::<_, Option<i64>>(10)?.unwrap_or_default(),
        is_deleted: int_to_bool(row.get::<_, Option<i64>>(11)?),
        deleted_at: row.get(12)?,
        item_count: row.get::<_, Option<i64>>(13)?.unwrap_or_default(),
    })
}

fn parse_optional_json_text(value: Option<&str>) -> Result<Option<Value>, PersistenceError> {
    let Some(raw) = value else {
        return Ok(None);
    };
    if raw.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(serde_json::from_str(raw)?))
}

fn int_to_bool(value: Option<i64>) -> bool {
    value.unwrap_or_default() != 0
}

fn bool_to_int(value: bool) -> i64 {
    if value { 1 } else { 0 }
}

fn utc_now_text() -> String {
    Utc::now().to_rfc3339()
}

fn next_server_version() -> i64 {
    Utc::now().timestamp_millis()
}

fn random_hex_token() -> String {
    let mut bytes = [0_u8; 16];
    rand::thread_rng().fill_bytes(&mut bytes);
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn parse_datetime_utc(value: &str) -> Option<DateTime<Utc>> {
    if value.trim().is_empty() {
        return None;
    }
    if let Ok(parsed) = DateTime::parse_from_rfc3339(value) {
        return Some(parsed.with_timezone(&Utc));
    }
    if let Ok(parsed) = DateTime::parse_from_rfc3339(&value.replace('Z', "+00:00")) {
        return Some(parsed.with_timezone(&Utc));
    }
    None
}

fn python_like_iso_text(value: Option<&str>) -> String {
    match value.and_then(parse_datetime_utc) {
        Some(parsed) => format!("{}Z", parsed.to_rfc3339()),
        None => match value {
            Some(raw) if raw.ends_with('Z') => raw.to_string(),
            Some(raw) if !raw.trim().is_empty() => format!("{raw}Z"),
            _ => format!("{}Z", Utc::now().to_rfc3339()),
        },
    }
}

fn python_like_iso_text_if_present(value: &str) -> String {
    python_like_iso_text(Some(value))
}

fn sync_entity_ordering(left: &SyncEntityRecord, right: &SyncEntityRecord) -> Ordering {
    left.server_version
        .cmp(&right.server_version)
        .then_with(|| sync_entity_id_key(&left.id).cmp(&sync_entity_id_key(&right.id)))
}

fn sync_entity_id_key(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Number(number) => number.to_string(),
        _ => value.to_string(),
    }
}

fn to_sql_error(error: PersistenceError) -> rusqlite::Error {
    rusqlite::Error::FromSqlConversionFailure(
        0,
        rusqlite::types::Type::Text,
        Box::new(error),
    )
}
