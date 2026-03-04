use std::env;
use std::io::{self, Read};

use bsr_pipeline_shadow::{
    build_chunk_sentence_plan_snapshot, build_chunk_synthesis_prompt_snapshot,
    build_chunking_preprocess_snapshot, build_content_cleaner_snapshot,
    build_extraction_adapter_snapshot, build_llm_wrapper_plan_snapshot,
    build_summary_aggregate_snapshot, build_summary_user_content_snapshot, ChunkSentencePlanInput,
    ChunkSynthesisPromptInput, ChunkingPreprocessInput, ContentCleanerInput,
    ExtractionAdapterInput, LlmWrapperPlanInput, SummaryAggregateInput, SummaryUserContentInput,
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
        "chunk-sentence-plan" => {
            let payload = read_json_stdin()?;
            let input: ChunkSentencePlanInput = serde_json::from_value(payload)?;
            let output = build_chunk_sentence_plan_snapshot(&input);
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
        "summary-aggregate" => {
            let payload = read_json_stdin()?;
            let input: SummaryAggregateInput = serde_json::from_value(payload)?;
            let output = build_summary_aggregate_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "chunk-synthesis-prompt" => {
            let payload = read_json_stdin()?;
            let input: ChunkSynthesisPromptInput = serde_json::from_value(payload)?;
            let output = build_chunk_synthesis_prompt_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "summary-user-content" => {
            let payload = read_json_stdin()?;
            let input: SummaryUserContentInput = serde_json::from_value(payload)?;
            let output = build_summary_user_content_snapshot(&input);
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-pipeline-shadow extraction-adapter < input.json");
            println!("  bsr-pipeline-shadow chunking-preprocess < input.json");
            println!("  bsr-pipeline-shadow chunk-sentence-plan < input.json");
            println!("  bsr-pipeline-shadow llm-wrapper-plan < input.json");
            println!("  bsr-pipeline-shadow content-cleaner < input.json");
            println!("  bsr-pipeline-shadow summary-aggregate < input.json");
            println!("  bsr-pipeline-shadow chunk-synthesis-prompt < input.json");
            println!("  bsr-pipeline-shadow summary-user-content < input.json");
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
