#!/usr/bin/env bash
set -euo pipefail

RATE="${RATE:-1}"
DURATION="${DURATION:-10s}"
ENDPOINT="${ENDPOINT:-https://pdf-extactext.universidad.localhost/extract}"

STRESS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF_PATH="${STRESS_DIR}/pdfs/documento_279_paginas.pdf"
RESULTS_DIR="${STRESS_DIR}/results"
TARGETS="${RESULTS_DIR}/test_carga.generated.txt"
BIN_OUTPUT="${RESULTS_DIR}/vegeta-results.bin"
JSON_OUTPUT="${RESULTS_DIR}/vegeta-results.json"
PLOT_OUTPUT="${RESULTS_DIR}/vegeta-plot.html"

if [[ ! -f "${PDF_PATH}" ]]; then
  echo "Falta el PDF real: ${PDF_PATH}" >&2
  exit 1
fi

if ! command -v vegeta >/dev/null 2>&1; then
  echo "Vegeta no esta instalado o no esta disponible en PATH." >&2
  exit 1
fi

mkdir -p "${RESULTS_DIR}"

cat >"${TARGETS}" <<EOF
POST ${ENDPOINT}
Content-Type: application/pdf
@${PDF_PATH}
EOF

vegeta attack \
  -insecure \
  -rate="${RATE}" \
  -duration="${DURATION}" \
  -targets="${TARGETS}" \
  | tee "${BIN_OUTPUT}" \
  | vegeta report

vegeta report -type=json <"${BIN_OUTPUT}" >"${JSON_OUTPUT}"
vegeta plot <"${BIN_OUTPUT}" >"${PLOT_OUTPUT}"

echo "Resultados generados en ${RESULTS_DIR}"
