use std::env;
use std::path::PathBuf;

use bsr_persistence::{
    ensure_migration_history_table, find_repo_migrations_dir, migration_status_report,
    open_connection,
};
use serde_json::json;

fn main() {
    if let Err(err) = run() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| "help".to_string());
    let remaining_args = args.collect::<Vec<_>>();

    match command.as_str() {
        "migration-status" => {
            let db_path = parse_required_arg(&remaining_args, "--db-path")?;
            let migrations_dir = parse_optional_arg(&remaining_args, "--migrations-dir")
                .map(PathBuf::from)
                .map(Ok)
                .unwrap_or_else(|| find_repo_migrations_dir(env::current_dir()?))?;
            let report = migration_status_report(db_path, migrations_dir)?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            Ok(())
        }
        "ensure-migration-table" => {
            let db_path = parse_required_arg(&remaining_args, "--db-path")?;
            let connection = open_connection(db_path)?;
            ensure_migration_history_table(&connection)?;
            println!(
                "{}",
                serde_json::to_string(&json!({
                    "ok": true,
                    "operation": "ensure-migration-table",
                }))?
            );
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-persistence migration-status --db-path /path/to/app.db [--migrations-dir /path/to/app/cli/migrations]");
            println!("  bsr-persistence ensure-migration-table --db-path /path/to/app.db");
            Ok(())
        }
    }
}

fn parse_required_arg(args: &[String], flag: &str) -> Result<String, std::io::Error> {
    if let Some(value) = parse_optional_arg(args, flag) {
        return Ok(value);
    }

    Err(std::io::Error::new(
        std::io::ErrorKind::InvalidInput,
        format!("missing {flag} argument"),
    ))
}

fn parse_optional_arg(args: &[String], flag: &str) -> Option<String> {
    args.windows(2)
        .find_map(|window| (window[0] == flag).then(|| window[1].clone()))
}
