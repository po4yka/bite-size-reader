use std::fs;
use std::path::{Path, PathBuf};

use bsr_pipeline_shadow::{
    build_chunk_sentence_plan_snapshot, build_chunk_synthesis_prompt_snapshot,
    build_chunking_preprocess_snapshot, build_content_cleaner_snapshot,
    build_extraction_adapter_snapshot, build_llm_wrapper_plan_snapshot,
    build_summary_aggregate_snapshot, build_summary_user_content_snapshot, ChunkSentencePlanInput,
    ChunkSynthesisPromptInput, ChunkingPreprocessInput, ContentCleanerInput,
    ExtractionAdapterInput, LlmWrapperPlanInput, SummaryAggregateInput, SummaryUserContentInput,
};
use serde_json::Value;

#[test]
fn m3_fixture_parity() {
    let fixture_root = project_root()
        .join("docs")
        .join("migration")
        .join("fixtures")
        .join("m3_pipeline_shadow");
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

        let input: Value = serde_json::from_str(
            &fs::read_to_string(&input_path).expect("should read input fixture"),
        )
        .expect("valid input fixture json");
        let expected: Value = serde_json::from_str(
            &fs::read_to_string(&expected_path).expect("should read expected fixture"),
        )
        .expect("valid expected fixture json");

        let actual = match fixture_name.as_str() {
            "extraction_adapter" => {
                let parsed: ExtractionAdapterInput =
                    serde_json::from_value(input).expect("valid extraction fixture");
                serde_json::to_value(build_extraction_adapter_snapshot(&parsed))
                    .expect("serialize extraction snapshot")
            }
            "chunking_preprocess" => {
                let parsed: ChunkingPreprocessInput =
                    serde_json::from_value(input).expect("valid chunking fixture");
                serde_json::to_value(build_chunking_preprocess_snapshot(&parsed))
                    .expect("serialize chunking snapshot")
            }
            "chunk_sentence_plan" => {
                let parsed: ChunkSentencePlanInput =
                    serde_json::from_value(input).expect("valid chunk sentence plan fixture");
                serde_json::to_value(build_chunk_sentence_plan_snapshot(&parsed))
                    .expect("serialize chunk sentence plan snapshot")
            }
            "llm_wrapper_plan" => {
                let parsed: LlmWrapperPlanInput =
                    serde_json::from_value(input).expect("valid llm wrapper fixture");
                serde_json::to_value(build_llm_wrapper_plan_snapshot(&parsed))
                    .expect("serialize llm wrapper snapshot")
            }
            "content_cleaner" => {
                let parsed: ContentCleanerInput =
                    serde_json::from_value(input).expect("valid content cleaner fixture");
                serde_json::to_value(build_content_cleaner_snapshot(&parsed))
                    .expect("serialize content cleaner snapshot")
            }
            "summary_aggregate" => {
                let parsed: SummaryAggregateInput =
                    serde_json::from_value(input).expect("valid summary aggregate fixture");
                serde_json::to_value(build_summary_aggregate_snapshot(&parsed))
                    .expect("serialize summary aggregate snapshot")
            }
            "chunk_synthesis_prompt" => {
                let parsed: ChunkSynthesisPromptInput =
                    serde_json::from_value(input).expect("valid chunk synthesis fixture");
                serde_json::to_value(build_chunk_synthesis_prompt_snapshot(&parsed))
                    .expect("serialize chunk synthesis snapshot")
            }
            "summary_user_content" => {
                let parsed: SummaryUserContentInput =
                    serde_json::from_value(input).expect("valid summary user-content fixture");
                serde_json::to_value(build_summary_user_content_snapshot(&parsed))
                    .expect("serialize summary user-content snapshot")
            }
            _ => panic!("unknown fixture name: {}", fixture_name),
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
