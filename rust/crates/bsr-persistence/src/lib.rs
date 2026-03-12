use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use bsr_models::{MigrationHistoryEntry, MigrationStatusEntry, MigrationStatusReport};
use rusqlite::Connection;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum PersistenceError {
    #[error("sqlite error: {0}")]
    Sqlite(#[from] rusqlite::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("could not locate app/cli/migrations from {start}")]
    MigrationsDirNotFound { start: String },
}

const MIGRATION_HISTORY_DDL: &str = r#"
CREATE TABLE IF NOT EXISTS "migration_history" (
    "migration_name" TEXT NOT NULL PRIMARY KEY,
    "applied_at" DATETIME NOT NULL,
    "rollback_sql" TEXT
)
"#;

pub fn open_connection(db_path: impl AsRef<Path>) -> Result<Connection, PersistenceError> {
    Ok(Connection::open(db_path)?)
}

pub fn ensure_migration_history_table(connection: &Connection) -> Result<(), PersistenceError> {
    connection.execute_batch(MIGRATION_HISTORY_DDL)?;
    Ok(())
}

pub fn list_applied_migrations(
    connection: &Connection,
) -> Result<Vec<MigrationHistoryEntry>, PersistenceError> {
    let mut statement = connection.prepare(
        r#"
        SELECT migration_name, applied_at, rollback_sql
        FROM migration_history
        ORDER BY migration_name
        "#,
    )?;

    let rows = statement.query_map([], |row| {
        Ok(MigrationHistoryEntry {
            migration_name: row.get(0)?,
            applied_at: row.get(1)?,
            rollback_sql: row.get(2)?,
        })
    })?;

    let mut entries = Vec::new();
    for row in rows {
        entries.push(row?);
    }
    Ok(entries)
}

pub fn list_repo_migration_names(
    migrations_dir: impl AsRef<Path>,
) -> Result<Vec<String>, PersistenceError> {
    let mut migrations = fs::read_dir(migrations_dir)?
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let path = entry.path();
            let file_name = path.file_name()?.to_str()?;
            if !is_python_migration_filename(file_name) {
                return None;
            }
            Some(path.file_stem()?.to_str()?.to_string())
        })
        .collect::<Vec<_>>();

    migrations.sort();
    Ok(migrations)
}

pub fn build_migration_status_report(
    repo_migrations: &[String],
    applied_migrations: &[MigrationHistoryEntry],
) -> MigrationStatusReport {
    let applied_lookup = applied_migrations
        .iter()
        .map(|entry| (entry.migration_name.clone(), entry.applied_at.clone()))
        .collect::<BTreeMap<_, _>>();

    let migrations = repo_migrations
        .iter()
        .map(|migration_name| MigrationStatusEntry {
            migration_name: migration_name.clone(),
            applied: applied_lookup.contains_key(migration_name),
            applied_at: applied_lookup.get(migration_name).cloned().flatten(),
        })
        .collect::<Vec<_>>();

    let applied = migrations.iter().filter(|entry| entry.applied).count();
    let total = migrations.len();

    MigrationStatusReport {
        total,
        applied,
        pending: total.saturating_sub(applied),
        migrations,
    }
}

pub fn migration_status_report(
    db_path: impl AsRef<Path>,
    migrations_dir: impl AsRef<Path>,
) -> Result<MigrationStatusReport, PersistenceError> {
    let connection = open_connection(db_path)?;
    ensure_migration_history_table(&connection)?;
    let applied = list_applied_migrations(&connection)?;
    let repo_migrations = list_repo_migration_names(migrations_dir)?;
    Ok(build_migration_status_report(&repo_migrations, &applied))
}

pub fn find_repo_migrations_dir(start: impl AsRef<Path>) -> Result<PathBuf, PersistenceError> {
    let start = start.as_ref();
    for candidate_root in start.ancestors() {
        let candidate = candidate_root.join("app").join("cli").join("migrations");
        if candidate.is_dir() {
            return Ok(candidate);
        }
        let nested_candidate = candidate_root
            .join("bite-size-reader")
            .join("app")
            .join("cli")
            .join("migrations");
        if nested_candidate.is_dir() {
            return Ok(nested_candidate);
        }
    }

    Err(PersistenceError::MigrationsDirNotFound {
        start: start.display().to_string(),
    })
}

fn is_python_migration_filename(file_name: &str) -> bool {
    let Some(stem) = file_name.strip_suffix(".py") else {
        return false;
    };
    if stem.len() < 5 {
        return false;
    }

    let mut chars = stem.chars();
    chars.by_ref().take(3).all(|ch| ch.is_ascii_digit()) && chars.next() == Some('_')
}

#[cfg(test)]
mod tests {
    use std::fs;

    use rusqlite::params;
    use tempfile::TempDir;

    use super::{
        build_migration_status_report, ensure_migration_history_table, find_repo_migrations_dir,
        list_applied_migrations, list_repo_migration_names, migration_status_report,
        open_connection,
    };
    use bsr_models::MigrationHistoryEntry;

    #[test]
    fn ensure_migration_history_table_matches_python_schema() {
        let dir = TempDir::new().expect("temp dir");
        let db_path = dir.path().join("app.db");
        let connection = open_connection(&db_path).expect("connection");

        ensure_migration_history_table(&connection).expect("ensure migration table");

        let mut statement = connection
            .prepare("PRAGMA table_info('migration_history')")
            .expect("table info statement");
        let rows = statement
            .query_map([], |row| {
                Ok((
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, i64>(3)?,
                    row.get::<_, i64>(5)?,
                ))
            })
            .expect("table info rows");

        let collected = rows
            .map(|row| row.expect("table info row"))
            .collect::<Vec<_>>();

        assert_eq!(
            collected,
            vec![
                ("migration_name".to_string(), "TEXT".to_string(), 1, 1),
                ("applied_at".to_string(), "DATETIME".to_string(), 1, 0),
                ("rollback_sql".to_string(), "TEXT".to_string(), 0, 0),
            ]
        );
    }

    #[test]
    fn list_repo_migration_names_ignores_non_matching_files() {
        let dir = TempDir::new().expect("temp dir");
        fs::write(dir.path().join("001_add_users.py"), "").expect("migration one");
        fs::write(dir.path().join("002_add_posts.py"), "").expect("migration two");
        fs::write(dir.path().join("__init__.py"), "").expect("init");
        fs::write(dir.path().join("notes.txt"), "").expect("notes");

        let migration_names = list_repo_migration_names(dir.path()).expect("migration names");

        assert_eq!(
            migration_names,
            vec!["001_add_users".to_string(), "002_add_posts".to_string()]
        );
    }

    #[test]
    fn build_migration_status_report_marks_pending_and_applied() {
        let report = build_migration_status_report(
            &[
                "001_add_users".to_string(),
                "002_add_posts".to_string(),
                "003_add_topics".to_string(),
            ],
            &[
                MigrationHistoryEntry {
                    migration_name: "001_add_users".to_string(),
                    applied_at: Some("2026-03-12T10:00:00".to_string()),
                    rollback_sql: None,
                },
                MigrationHistoryEntry {
                    migration_name: "002_add_posts".to_string(),
                    applied_at: Some("2026-03-12T11:00:00".to_string()),
                    rollback_sql: None,
                },
            ],
        );

        assert_eq!(report.total, 3);
        assert_eq!(report.applied, 2);
        assert_eq!(report.pending, 1);
        assert_eq!(report.migrations[2].migration_name, "003_add_topics");
        assert!(!report.migrations[2].applied);
    }

    #[test]
    fn migration_status_report_reads_db_and_repo_inventory() {
        let dir = TempDir::new().expect("temp dir");
        let migrations_dir = dir.path().join("migrations");
        fs::create_dir_all(&migrations_dir).expect("migrations dir");
        fs::write(migrations_dir.join("001_add_users.py"), "").expect("migration one");
        fs::write(migrations_dir.join("002_add_posts.py"), "").expect("migration two");

        let db_path = dir.path().join("app.db");
        let connection = open_connection(&db_path).expect("connection");
        ensure_migration_history_table(&connection).expect("ensure migration table");
        connection
            .execute(
                "INSERT INTO migration_history (migration_name, applied_at, rollback_sql) VALUES (?1, ?2, ?3)",
                params!["001_add_users", "2026-03-12T10:00:00", Option::<String>::None],
            )
            .expect("insert migration");

        let report = migration_status_report(&db_path, &migrations_dir).expect("status report");

        assert_eq!(report.total, 2);
        assert_eq!(report.applied, 1);
        assert_eq!(report.pending, 1);
        assert_eq!(report.migrations[0].migration_name, "001_add_users");
        assert!(report.migrations[0].applied);
        assert_eq!(report.migrations[1].migration_name, "002_add_posts");
        assert!(!report.migrations[1].applied);
    }

    #[test]
    fn list_applied_migrations_returns_sorted_rows() {
        let dir = TempDir::new().expect("temp dir");
        let db_path = dir.path().join("app.db");
        let connection = open_connection(&db_path).expect("connection");
        ensure_migration_history_table(&connection).expect("ensure migration table");
        connection
            .execute(
                "INSERT INTO migration_history (migration_name, applied_at, rollback_sql) VALUES (?1, ?2, ?3)",
                params!["002_add_posts", "2026-03-12T11:00:00", Option::<String>::None],
            )
            .expect("insert second");
        connection
            .execute(
                "INSERT INTO migration_history (migration_name, applied_at, rollback_sql) VALUES (?1, ?2, ?3)",
                params!["001_add_users", "2026-03-12T10:00:00", Option::<String>::None],
            )
            .expect("insert first");

        let applied = list_applied_migrations(&connection).expect("applied migrations");

        assert_eq!(applied.len(), 2);
        assert_eq!(applied[0].migration_name, "001_add_users");
        assert_eq!(applied[1].migration_name, "002_add_posts");
    }

    #[test]
    fn find_repo_migrations_dir_walks_up_to_repo_layout() {
        let dir = TempDir::new().expect("temp dir");
        let nested = dir
            .path()
            .join("repo")
            .join("rust")
            .join("crates")
            .join("bsr-persistence");
        let migrations_dir = dir
            .path()
            .join("repo")
            .join("app")
            .join("cli")
            .join("migrations");
        fs::create_dir_all(&nested).expect("nested dir");
        fs::create_dir_all(&migrations_dir).expect("migrations dir");

        let found = find_repo_migrations_dir(&nested).expect("found migrations dir");

        assert_eq!(found, migrations_dir);
    }
}
