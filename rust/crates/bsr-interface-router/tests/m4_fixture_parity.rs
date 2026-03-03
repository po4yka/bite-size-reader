use std::fs;
use std::path::{Path, PathBuf};

use bsr_interface_router::{
    resolve_mobile_route, resolve_telegram_command, MobileRouteInput, TelegramCommandInput,
};
use serde_json::Value;

#[test]
fn m4_fixture_parity() {
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
        let payload = input
            .get("payload")
            .cloned()
            .expect("fixture payload should be present");

        let actual = match fixture_type {
            "mobile_route" => {
                let parsed: MobileRouteInput =
                    serde_json::from_value(payload).expect("valid mobile_route payload");
                serde_json::to_value(resolve_mobile_route(&parsed))
                    .expect("serialize mobile route decision")
            }
            "telegram_command" => {
                let parsed: TelegramCommandInput =
                    serde_json::from_value(payload).expect("valid telegram_command payload");
                serde_json::to_value(resolve_telegram_command(&parsed))
                    .expect("serialize telegram command decision")
            }
            _ => panic!("unsupported fixture type: {}", fixture_type),
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
