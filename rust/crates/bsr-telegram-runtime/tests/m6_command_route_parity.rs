use std::fs;
use std::path::{Path, PathBuf};

use bsr_telegram_runtime::{resolve_command_route, TelegramCommandRouteInput};
use serde_json::Value;

#[test]
fn command_route_matches_m4_telegram_command_fixtures() {
    let fixture_root = project_root()
        .join("docs")
        .join("migration")
        .join("fixtures")
        .join("m4_interface_routing");
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

        let fixture_type = input
            .get("type")
            .and_then(Value::as_str)
            .expect("fixture type should be present");
        if fixture_type != "telegram_command" {
            continue;
        }

        let payload = input
            .get("payload")
            .cloned()
            .expect("fixture payload should be present");

        let parsed: TelegramCommandRouteInput =
            serde_json::from_value(payload).expect("valid telegram command payload");
        let actual = serde_json::to_value(resolve_command_route(&parsed))
            .expect("serialize telegram command decision");

        assert_eq!(actual, expected, "fixture mismatch for {}", fixture_name);
    }
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}
