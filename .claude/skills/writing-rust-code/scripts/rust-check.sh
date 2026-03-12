#!/usr/bin/env bash
# Quick Rust workspace health check for dynamic context injection.
# Designed to complete fast on warm cache; fails gracefully if cargo unavailable.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Walk up to find rust/Cargo.toml relative to script or cwd
MANIFEST=""
for base in "$SCRIPT_DIR/../../../../rust" "$(pwd)/rust"; do
  if [ -f "$base/Cargo.toml" ]; then
    MANIFEST="$base/Cargo.toml"
    break
  fi
done

if [ -z "$MANIFEST" ]; then
  echo "Rust workspace: Cargo.toml not found"
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "Rust workspace: cargo not available"
  exit 1
fi

WORKSPACE_DIR="$(dirname "$MANIFEST")"

# List crates via cargo metadata
CRATES=$(cargo metadata --no-deps --manifest-path "$MANIFEST" 2>/dev/null \
  | python3 -c "import sys,json; pkgs=json.load(sys.stdin)['packages']; print(f'crates={len(pkgs)}: ' + ', '.join(sorted(p['name'] for p in pkgs)))" 2>/dev/null \
  || echo "crates=? (metadata unavailable)")
echo "Rust workspace: $CRATES"

# Quick type check (no codegen)
if cargo check --workspace --manifest-path "$MANIFEST" 2>/dev/null; then
  echo "cargo check: OK"
else
  echo "cargo check: FAILED"
fi

# Count tests
TEST_COUNT=$(cargo test --workspace --manifest-path "$MANIFEST" -- --list 2>/dev/null \
  | grep -c ': test$' || echo "0")
echo "tests: $TEST_COUNT"
