#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INPUT_DIR="$ROOT_DIR/data/cleaned_html_2"
OUTPUT_DIR="$ROOT_DIR/data/nkg_chunked_local_2"

PYTHON_BIN="${PYTHON_BIN:-python}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
MODEL="${MODEL:-gemma4:31b}"
PARALLEL_WORKERS="${PARALLEL_WORKERS:-2}"

mkdir -p "$OUTPUT_DIR"

shopt -s nullglob
files=("$INPUT_DIR"/*.html)

if ((${#files[@]} == 0)); then
  echo "No HTML files found in $INPUT_DIR"
  exit 1
fi

echo "Input dir : $INPUT_DIR"
echo "Output dir: $OUTPUT_DIR"
echo "Python    : $PYTHON_BIN"
echo "Model     : $MODEL"
echo "Workers   : $PARALLEL_WORKERS"
echo

for f in "${files[@]}"; do
  base="$(basename "${f%.html}")"
  out="$OUTPUT_DIR/$base.nkg.json"
  file_size=$(wc -c < "$f")

  # Skip global reconcile for files larger than 100KB — full HTML is too big for Ollama
  if (( file_size > 100000 )); then
    reconcile_flag=""
  else
    reconcile_flag="--global-reconcile-pass"
  fi

  echo "=== Processing: $(basename "$f") (${file_size} bytes) ==="
  "$PYTHON_BIN" "$SCRIPT_DIR/chunked_html_to_nkg.py" \
    --backend local \
    --ollama-url "$OLLAMA_URL" \
    --model "$MODEL" \
    --html "$f" \
    --out "$out" \
    --parallel-chunks \
    --parallel-workers "$PARALLEL_WORKERS" \
    --chunk-chars 12000 \
    --num-predict 8192 \
    --patch-missing \
    $reconcile_flag \
    --selector-validate \
    --selector-repair-pass \
    --selector-repair-max 120 \
    --log-file ./output.log

done

echo
 echo "Done."
