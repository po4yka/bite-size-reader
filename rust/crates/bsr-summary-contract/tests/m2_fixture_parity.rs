use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

use bsr_summary_contract::{
    check_sqlite_compatibility, sqlite_roundtrip_smoke, validate_and_shape_summary,
};
use serde_json::{json, Map, Value};
use tempfile::NamedTempFile;

#[test]
fn m2_fixture_shape_and_subset_parity() {
    let fixture_root = project_root()
        .join("docs")
        .join("migration")
        .join("fixtures")
        .join("m2_summary_contract");
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

        let output = validate_and_shape_summary(&input).expect("rust shaping should succeed");

        let expected_shape = expected
            .get("shape")
            .cloned()
            .expect("expected fixture should include shape");
        let actual_shape = shape_signature(&output);
        assert_eq!(
            actual_shape, expected_shape,
            "shape mismatch for fixture {}",
            fixture_name
        );

        let expected_subset = expected
            .get("subset")
            .and_then(Value::as_object)
            .expect("expected fixture should include subset");
        let output_obj = output
            .as_object()
            .expect("contract output should always be an object");

        for (key, expected_value) in expected_subset {
            let actual = output_obj
                .get(key)
                .unwrap_or_else(|| panic!("missing subset key {key} in fixture {fixture_name}"));
            assert_eq!(
                actual, expected_value,
                "subset mismatch for key '{}' in fixture {}",
                key, fixture_name
            );
        }
    }
}

#[test]
fn sqlite_schema_compatibility_matches_python_snapshot() {
    let snapshot = project_root().join("app_backup.db");
    assert!(
        snapshot.is_file(),
        "expected sqlite snapshot at {:?}",
        snapshot
    );

    let report = check_sqlite_compatibility(&snapshot).expect("sqlite compatibility check");
    assert!(
        report.compatible,
        "snapshot schema should be compatible: {:?}",
        report
    );

    let tmp = NamedTempFile::new().expect("temporary sqlite copy");
    fs::copy(&snapshot, tmp.path()).expect("copy sqlite snapshot");
    sqlite_roundtrip_smoke(tmp.path()).expect("sqlite roundtrip should succeed");
}

fn project_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
}

fn shape_signature(value: &Value) -> Value {
    match value {
        Value::Null => json!({"type": "null"}),
        Value::Bool(_) => json!({"type": "bool"}),
        Value::Number(_) => json!({"type": "number"}),
        Value::String(_) => json!({"type": "string"}),
        Value::Array(items) => {
            if items.is_empty() {
                return json!({"type": "array", "item": {"type": "any"}});
            }

            let mut variants: Vec<Value> = Vec::new();
            let mut seen = HashSet::new();
            for item in items {
                let shape = shape_signature(item);
                let signature = serde_json::to_string(&shape).expect("shape serialization");
                if seen.insert(signature) {
                    variants.push(shape);
                }
            }

            let item_shape = if variants.len() == 1 {
                variants.remove(0)
            } else {
                json!({"type": "union", "variants": variants})
            };

            json!({"type": "array", "item": item_shape})
        }
        Value::Object(map) => {
            let mut fields = Map::new();
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            for key in keys {
                fields.insert(
                    key.clone(),
                    shape_signature(map.get(key).expect("key exists")),
                );
            }

            let mut out = Map::new();
            out.insert("type".to_string(), Value::String("object".to_string()));
            out.insert("fields".to_string(), Value::Object(fields));
            Value::Object(out)
        }
    }
}
