$RATE = "1"
$DURATION = "10s"
$ENDPOINT = "https://pdf-extactext.universidad.localhost/extract"

$STRESS_DIR = $PSScriptRoot
$PDF_PATH = Join-Path $STRESS_DIR "pdfs\documento_279_paginas.pdf"
$RESULTS_DIR = Join-Path $STRESS_DIR "results"
$TARGETS = Join-Path $RESULTS_DIR "test_carga.generated.txt"
$BIN_OUTPUT = Join-Path $RESULTS_DIR "vegeta-results.bin"
$JSON_OUTPUT = Join-Path $RESULTS_DIR "vegeta-results.json"
$PLOT_OUTPUT = Join-Path $RESULTS_DIR "vegeta-plot.html"

if (-not (Test-Path -LiteralPath $PDF_PATH -PathType Leaf)) {
    throw "Falta el PDF real: $PDF_PATH"
}

if (-not (Get-Command vegeta -ErrorAction SilentlyContinue)) {
    throw "Vegeta no esta instalado o no esta disponible en PATH."
}

New-Item -ItemType Directory -Path $RESULTS_DIR -Force | Out-Null
$PDF_ABSOLUTE_PATH = (Resolve-Path -LiteralPath $PDF_PATH).Path

$TARGET_CONTENT = @"
POST $ENDPOINT
Content-Type: application/pdf
@$PDF_ABSOLUTE_PATH
"@
Set-Content -LiteralPath $TARGETS -Value $TARGET_CONTENT -NoNewline -Encoding utf8

$ATTACK_ARGUMENTS = @(
    "attack",
    "-insecure",
    "-rate=$RATE",
    "-duration=$DURATION",
    "-targets=$TARGETS"
)
$ATTACK_PROCESS = Start-Process \
    -FilePath "vegeta" \
    -ArgumentList $ATTACK_ARGUMENTS \
    -NoNewWindow \
    -Wait \
    -PassThru \
    -RedirectStandardOutput $BIN_OUTPUT

if ($ATTACK_PROCESS.ExitCode -ne 0) {
    throw "vegeta attack finalizo con codigo $($ATTACK_PROCESS.ExitCode)."
}

& vegeta report $BIN_OUTPUT
if ($LASTEXITCODE -ne 0) {
    throw "vegeta report no pudo leer $BIN_OUTPUT."
}

& vegeta report -type=json $BIN_OUTPUT | Set-Content -LiteralPath $JSON_OUTPUT -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    throw "vegeta report no pudo generar $JSON_OUTPUT."
}

& vegeta plot $BIN_OUTPUT | Set-Content -LiteralPath $PLOT_OUTPUT -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    throw "vegeta plot no pudo generar $PLOT_OUTPUT."
}

Write-Host "Resultados generados en $RESULTS_DIR"
