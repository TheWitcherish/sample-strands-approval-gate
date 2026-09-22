#!/usr/bin/env bash
# Certification run for the approval gate.
# Runs the sample in both directions against Amazon Bedrock and asserts on
# the printed trace. Deterministic assertions only, no judge model.
set -euo pipefail

cd "$(dirname "$0")"

approved="$(APPROVE=y uv run python approval_gate.py)"
denied="$(APPROVE=n uv run python approval_gate.py)"

failures=0

count_lines() {
    # grep -c exits 1 on zero matches; the count is still the answer we want.
    grep -c -F -- "$1" <<<"$2" || true
}

assert_count() {
    local label="$1" actual="$2" expected="$3"
    if [ "$actual" -eq "$expected" ]; then
        echo "PASS  $label: $actual"
    else
        echo "FAIL  $label: expected $expected, got $actual"
        failures=$((failures + 1))
    fi
}

assert_count "approved run, TOOL EXECUTED lines" \
    "$(count_lines 'TOOL EXECUTED' "$approved")" 1
assert_count "denied run, TOOL EXECUTED lines" \
    "$(count_lines 'TOOL EXECUTED' "$denied")" 0
assert_count "approved run, FINAL   stop_reason=end_turn lines" \
    "$(count_lines 'FINAL   stop_reason=end_turn' "$approved")" 1
assert_count "denied run, FINAL   stop_reason=end_turn lines" \
    "$(count_lines 'FINAL   stop_reason=end_turn' "$denied")" 1

if [ "$failures" -ne 0 ]; then
    echo "FAIL  $failures assertion(s) failed"
    exit 1
fi
echo "PASS  gate certified"
