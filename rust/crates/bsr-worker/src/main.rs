use std::env;
use std::io::{self, Read};

use bsr_worker::{
    execute_forward_text, execute_url_single_pass, OpenRouterRuntimeConfig, WorkerExecutionInput,
};

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
        "url-single-pass" => {
            let input: WorkerExecutionInput = serde_json::from_value(read_json_stdin()?)?;
            let config = OpenRouterRuntimeConfig::from_env()?;
            let output = execute_url_single_pass(&input, &config).await?;
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        "forward-text" => {
            let input: WorkerExecutionInput = serde_json::from_value(read_json_stdin()?)?;
            let config = OpenRouterRuntimeConfig::from_env()?;
            let output = execute_forward_text(&input, &config).await?;
            println!("{}", serde_json::to_string_pretty(&output)?);
            Ok(())
        }
        _ => {
            println!("Usage:");
            println!("  bsr-worker url-single-pass < input.json");
            println!("  bsr-worker forward-text < input.json");
            Ok(())
        }
    }
}

fn read_json_stdin() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    Ok(serde_json::from_str(&input)?)
}
