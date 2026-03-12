use std::fs;
use std::path::{Path, PathBuf};

use bsr_processing_orchestrator::{
    build_forward_processing_plan, build_url_processing_plan, ForwardProcessingPlanInput,
    UrlProcessingPlanInput,
};
use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Deserialize)]
struct FixtureEnvelope {
    #[serde(rename = "type")]
    fixture_type: String,
    payload: Value,
}

#[test]
fn processing_orchestrator_fixture_parity() {
    let fixture_root = project_root()
        .join("docs")
        .join("migration")
        .join("fixtures")
        .join("processing_orchestrator");
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

        let actual = match envelope.fixture_type.as_str() {
            "url_plan" => {
                let parsed: UrlProcessingPlanInput =
                    serde_json::from_value(envelope.payload).expect("valid url-plan fixture");
                serde_json::to_value(build_url_processing_plan(&parsed))
                    .expect("serialize url-plan fixture")
            }
            "forward_plan" => {
                let parsed: ForwardProcessingPlanInput =
                    serde_json::from_value(envelope.payload).expect("valid forward-plan fixture");
                serde_json::to_value(build_forward_processing_plan(&parsed))
                    .expect("serialize forward-plan fixture")
            }
            _ => panic!("unknown fixture type: {}", envelope.fixture_type),
        };

        assert_eq!(actual, expected, "fixture mismatch for {}", fixture_name);
    }
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}
