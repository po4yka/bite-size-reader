use std::env;
use std::io::{self, Read};

use bsr_summary_contract::{
    check_sqlite_compatibility, sqlite_roundtrip_smoke, validate_and_shape_summary,
};
use serde_json::{json, Value};

fn main() {
    if let Err(err) = run() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| "help".to_string());

    match command.as_str() {
        "normalize" => {
            let mut input = String::new();
            io::stdin().read_to_string(&mut input)?;
            let payload: Value = serde_json::from_str(&input)?;
            let shaped = validate_and_shape_summary(&payload)?;
            println!("{}", serde_json::to_string_pretty(&shaped)?);
            Ok(())
        }
        "sqlite-check" => {
            let db_path = parse_db_path(args)?;
            let report = check_sqlite_compatibility(db_path)?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            Ok(())
        }
        "sqlite-roundtrip" => {
            let db_path = parse_db_path(args)?;
            sqlite_roundtrip_smoke(db_path)?;
            println!(
                "{}",
                serde_json::to_string_pretty(
                    &json!({"ok": true, "operation": "sqlite-roundtrip"})
                )?
            );
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-summary-contract normalize < input.json");
            println!("  bsr-summary-contract sqlite-check --db-path /path/to/app.db");
            println!("  bsr-summary-contract sqlite-roundtrip --db-path /path/to/app.db");
            Ok(())
        }
    }
}

fn parse_db_path(mut args: impl Iterator<Item = String>) -> Result<String, io::Error> {
    while let Some(arg) = args.next() {
        if arg == "--db-path" {
            if let Some(path) = args.next() {
                return Ok(path);
            }
            break;
        }
    }

    Err(io::Error::new(
        io::ErrorKind::InvalidInput,
        "missing --db-path argument",
    ))
}
