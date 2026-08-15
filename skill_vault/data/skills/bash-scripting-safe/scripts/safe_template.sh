#!/usr/bin/env bash
# safe_template.sh — Production-ready bash script skeleton
#
# Usage: ./safe_template.sh <input_dir> <output_dir>
# Demonstrates: set -euo pipefail, arg validation, mktemp, traps, atomic writes.

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────

readonly SCRIPT_NAME="$(basename "$0")"

# ── Functions ───────────────────────────────────────────────────────────

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: $SCRIPT_NAME INPUT_DIR OUTPUT_DIR

Processes files from INPUT_DIR and writes results to OUTPUT_DIR.
EOF
    exit 0
}

# ── Argument validation ─────────────────────────────────────────────────

[[ "$#" -eq 2 ]] || usage

INPUT_DIR="$1"
OUTPUT_DIR="$2"

[[ -d "$INPUT_DIR" ]] || die "INPUT_DIR '$INPUT_DIR' is not a directory"
mkdir -p "$OUTPUT_DIR"

# ── Dependency check ────────────────────────────────────────────────────

for cmd in jq wc; do
    command -v "$cmd" >/dev/null 2>&1 || die "'$cmd' is required but not installed"
done

# ── Trap for cleanup ────────────────────────────────────────────────────

TMPFILE="$(mktemp)" || die "mktemp failed"
trap 'rm -f "$TMPFILE"' EXIT

# ── Main processing ─────────────────────────────────────────────────────

echo "[$SCRIPT_NAME] Processing files in '$INPUT_DIR' ..."

count=0
for f in "$INPUT_DIR"/*.txt; do
    [[ -f "$f" ]] || continue
    basename="$(basename "$f")"
    out="$OUTPUT_DIR/$basename"

    # Example: count lines and write a summary
    wc -l < "$f" > "$TMPFILE"

    # Atomic write: write to temp, then mv (never > straight onto the target)
    mv "$TMPFILE" "$out"
    ((count++))
done

echo "[$SCRIPT_NAME] Done. Processed $count file(s)."
