use std::env;
use std::io::{self, Read};

use bsr_processing_orchestrator::{
    build_forward_processing_plan, build_url_processing_plan, ForwardProcessingPlanInput,
    UrlProcessingPlanInput,
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
        "url-plan" => {
            let payload = read_json_stdin()?;
            let input: UrlProcessingPlanInput = serde_json::from_value(payload)?;
            let output = build_url_processing_plan(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "forward-plan" => {
            let payload = read_json_stdin()?;
            let input: ForwardProcessingPlanInput = serde_json::from_value(payload)?;
            let output = build_forward_processing_plan(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-processing-orchestrator url-plan < input.json");
            println!("  bsr-processing-orchestrator forward-plan < input.json");
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
