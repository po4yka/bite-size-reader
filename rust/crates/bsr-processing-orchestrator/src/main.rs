use std::env;
use std::io::{self, Read};

use bsr_processing_orchestrator::{
    build_forward_processing_plan, build_url_processing_plan, execute_forward_flow,
    execute_url_flow, write_ndjson_event, ForwardExecuteInput, ForwardProcessingPlanInput,
    OrchestratorEvent, UrlExecuteInput, UrlProcessingPlanInput,
};
use serde_json::Value;

#[tokio::main]
async fn main() {
    if let Err(err) = run().await {
        eprintln!("{err}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
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
        "url-execute" => {
            let input: UrlExecuteInput = serde_json::from_value(read_json_stdin()?)?;
            let stdout = io::stdout();
            let mut lock = stdout.lock();
            let mut emit = |event: OrchestratorEvent| write_ndjson_event(&mut lock, &event);
            let _ = execute_url_flow(&input, &mut emit).await?;
            Ok(())
        }
        "forward-execute" => {
            let input: ForwardExecuteInput = serde_json::from_value(read_json_stdin()?)?;
            let stdout = io::stdout();
            let mut lock = stdout.lock();
            let mut emit = |event: OrchestratorEvent| write_ndjson_event(&mut lock, &event);
            let _ = execute_forward_flow(&input, &mut emit).await?;
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-processing-orchestrator url-plan < input.json");
            println!("  bsr-processing-orchestrator forward-plan < input.json");
            println!("  bsr-processing-orchestrator url-execute < input.json");
            println!("  bsr-processing-orchestrator forward-execute < input.json");
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
