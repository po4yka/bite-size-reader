use std::env;
use std::io::{self, Read};

use bsr_pipeline_shadow::{
    build_chunking_preprocess_snapshot, build_content_cleaner_snapshot,
    build_extraction_adapter_snapshot, build_llm_wrapper_plan_snapshot, ChunkingPreprocessInput,
    ContentCleanerInput, ExtractionAdapterInput, LlmWrapperPlanInput,
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
        "extraction-adapter" => {
            let payload = read_json_stdin()?;
            let input: ExtractionAdapterInput = serde_json::from_value(payload)?;
            let output = build_extraction_adapter_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "chunking-preprocess" => {
            let payload = read_json_stdin()?;
            let input: ChunkingPreprocessInput = serde_json::from_value(payload)?;
            let output = build_chunking_preprocess_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "llm-wrapper-plan" => {
            let payload = read_json_stdin()?;
            let input: LlmWrapperPlanInput = serde_json::from_value(payload)?;
            let output = build_llm_wrapper_plan_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "content-cleaner" => {
            let payload = read_json_stdin()?;
            let input: ContentCleanerInput = serde_json::from_value(payload)?;
            let output = build_content_cleaner_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-pipeline-shadow extraction-adapter < input.json");
            println!("  bsr-pipeline-shadow chunking-preprocess < input.json");
            println!("  bsr-pipeline-shadow llm-wrapper-plan < input.json");
            println!("  bsr-pipeline-shadow content-cleaner < input.json");
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
