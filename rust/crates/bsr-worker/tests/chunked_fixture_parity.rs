use std::fs;
use std::path::{Path, PathBuf};

use bsr_summary_contract::validate_and_shape_summary;
use bsr_worker::{finalize_chunked_url_execution, WorkerAttemptOutcome, WorkerLlmCallResult};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Debug, Deserialize)]
struct FixtureEnvelope {
    #[serde(rename = "type")]
    fixture_type: String,
    payload: ChunkedFixturePayload,
}

#[derive(Debug, Deserialize)]
struct ChunkedFixturePayload {
    chunk_attempts: Vec<FixtureAttempt>,
    synthesis_attempt: Option<FixtureAttempt>,
}

#[derive(Debug, Deserialize)]
struct FixtureAttempt {
    preset_name: Option<String>,
    summary: Option<Value>,
    error_text: Option<String>,
}

#[test]
fn chunked_worker_fixture_parity() {
    let fixture_root = project_root()
        .join("docs")
        .join("migration")
        .join("fixtures")
        .join("worker_chunked");
    let input_dir = fixture_root.join("input");
    let expected_dir = fixture_root.join("expected");

    let mut input_files: Vec<PathBuf> = fs::read_dir(&input_dir)
        .expect("fixture input dir should exist")
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect();
    input_files.sort();

    assert!(
        !input_files.is_empty(),
        "expected at least one fixture in {:?}",
        input_dir
    );

    for input_path in input_files {
        let fixture_name = input_path
            .file_stem()
            .and_then(|stem| stem.to_str())
            .expect("fixture name")
            .to_string();
        let expected_path = expected_dir.join(format!("{fixture_name}.json"));

        let envelope: FixtureEnvelope = serde_json::from_str(
            &fs::read_to_string(&input_path).expect("should read input fixture"),
        )
        .expect("valid input fixture json");
        let expected: Value = serde_json::from_str(
            &fs::read_to_string(&expected_path).expect("should read expected fixture"),
        )
        .expect("valid expected fixture json");

        assert_eq!(
            envelope.fixture_type, "chunked_url_finalization",
            "unknown fixture type for {}",
            fixture_name
        );

        let actual = serde_json::to_value(finalize_chunked_url_execution(
            envelope
                .payload
                .chunk_attempts
                .into_iter()
                .map(build_attempt_outcome)
                .collect(),
            envelope
                .payload
                .synthesis_attempt
                .map(build_attempt_outcome),
        ))
        .expect("serialize chunked fixture output");

        assert_eq!(
            normalize_value(actual),
            normalize_value(expected),
            "fixture mismatch for {}",
            fixture_name
        );
    }
}

fn build_attempt_outcome(input: FixtureAttempt) -> WorkerAttemptOutcome {
    let status = if input.error_text.is_some() {
        "error"
    } else {
        "ok"
    };
    let error_context = input.error_text.as_ref().map(|error_text| {
        json!({
            "status_code": Value::Null,
            "message": error_text,
            "api_error": error_text,
            "request_id": Value::Null,
            "surface": "chunked_url",
        })
    });

    WorkerAttemptOutcome {
        preset_name: input.preset_name,
        model_override: None,
        llm_result: WorkerLlmCallResult {
            status: status.to_string(),
            model: Some("fixture-model".to_string()),
            response_text: None,
            response_json: None,
            openrouter_response_text: None,
            openrouter_response_json: None,
            tokens_prompt: None,
            tokens_completion: None,
            cost_usd: None,
            latency_ms: None,
            error_text: input.error_text,
            request_headers: None,
            request_messages: None,
            endpoint: "/api/v1/chat/completions".to_string(),
            structured_output_used: true,
            structured_output_mode: Some("json_object".to_string()),
            error_context,
        },
        summary: input
            .summary
            .as_ref()
            .and_then(|summary| validate_and_shape_summary(summary).ok()),
    }
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn normalize_value(value: Value) -> Value {
    match value {
        Value::Array(items) => Value::Array(items.into_iter().map(normalize_value).collect()),
        Value::Object(map) => Value::Object(
            map.into_iter()
                .map(|(key, value)| (key, normalize_value(value)))
                .collect(),
        ),
        Value::Number(number) => {
            if let Some(float_value) = number.as_f64() {
                json!((float_value * 1_000_000.0).round() / 1_000_000.0)
            } else {
                Value::Number(number)
            }
        }
        other => other,
    }
}
