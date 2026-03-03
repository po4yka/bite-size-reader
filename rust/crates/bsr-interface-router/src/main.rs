use std::env;
use std::io::{self, Read};

use bsr_interface_router::{
    resolve_mobile_route, resolve_telegram_command, MobileRouteInput, TelegramCommandInput,
};
use serde_json::Value;

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
        "mobile-route" => {
            let payload = read_json_stdin()?;
            let input: MobileRouteInput = serde_json::from_value(payload)?;
            let output = resolve_mobile_route(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "telegram-command" => {
            let payload = read_json_stdin()?;
            let input: TelegramCommandInput = serde_json::from_value(payload)?;
            let output = resolve_telegram_command(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-interface-router mobile-route < input.json");
            println!("  bsr-interface-router telegram-command < input.json");
            Ok(())
        }
    }
}

fn read_json_stdin() -> Result<Value, Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let payload = serde_json::from_str::<Value>(&input)?;
    Ok(payload)
}
