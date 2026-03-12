use bsr_mobile_api::{build_state_from_env, openapi_json, route_manifest_json, serve};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let command = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "serve".to_string());

    let state = build_state_from_env().await?;

    match command.as_str() {
        "serve" => serve(state).await?,
        "route-manifest" => {
            println!(
                "{}",
                serde_json::to_string_pretty(&route_manifest_json(&state))?
            );
        }
        "openapi-json" => {
            println!("{}", serde_json::to_string_pretty(openapi_json(&state))?);
        }
        other => {
            let msg = format!(
                "unknown bsr-api command: {other}. expected one of serve, route-manifest, openapi-json"
            );
            return Err(msg.into());
        }
    }

    Ok(())
}
