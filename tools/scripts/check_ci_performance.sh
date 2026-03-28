#!/usr/bin/env bash
# Check CI performance metrics after Phase 1 optimization
# Usage: ./tools/scripts/check_ci_performance.sh

set -euo pipefail

echo "=== CI Performance Metrics ==="
echo

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) is not installed"
    echo "Install: https://cli.github.com/"
    exit 1
fi

# Check last 10 successful CI runs
echo "📊 Last 10 successful CI runs:"
echo
gh run list --workflow=ci.yml --limit 10 --json conclusion,durationMs,createdAt,headBranch \
  | jq -r '.[] | select(.conclusion=="success") |
    "\(.createdAt | split("T")[0]) | \(.headBranch) | \(.durationMs/1000/60 | floor) min"' \
  | column -t -s '|'

echo
echo "📈 Average CI time (last 10 successful runs):"
gh run list --workflow=ci.yml --limit 10 --json conclusion,durationMs | \
  jq '[.[] | select(.conclusion=="success") | .durationMs/1000/60] | add / length | floor' | \
  awk '{print $1 " minutes"}'

echo
echo "🎯 Target metrics:"
echo "  - Main branch (all checks + Docker): 45-50 min (warm cache)"
echo "  - PR without Docker changes: 20-25 min (warm cache)"
echo "  - PR with Docker changes: 40-45 min (warm cache)"

echo
echo "🔍 Check specific run details:"
echo "  gh run view <run-id> --log | grep 'Cache restored' | wc -l"
echo "  gh run view <run-id> --web"
