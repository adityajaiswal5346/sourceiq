#!/usr/bin/env bash
# Remove packages duplicated by the Lambda python3.12 runtime.
# Run after: sam build && before: sam deploy
set -euo pipefail

BUILD_DIR="${1:-.aws-sam/build/DocuMindApi}"

if [[ ! -d "$BUILD_DIR" ]]; then
  echo "Build dir not found: $BUILD_DIR (run sam build first)" >&2
  exit 1
fi

while IFS= read -r pattern; do
  [[ -z "$pattern" || "$pattern" =~ ^# ]] && continue
  find "$BUILD_DIR" -maxdepth 1 \( -name "$pattern" -o -name "${pattern%.dist-info}.dist-info" \) -exec rm -rf {} + 2>/dev/null || true
done < "$(dirname "$0")/../lambdaignore"

echo "Pruned Lambda package at $BUILD_DIR"
