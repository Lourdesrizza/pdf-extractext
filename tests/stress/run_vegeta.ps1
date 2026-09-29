param(
    [ValidateSet(90, 279)]
    [int]$PdfPages = 279
)

$ErrorActionPreference = "Stop"
$RATE = "1"
$DURATION = "10s"
$ENDPOINT = "https://pdf-extactext.universidad.localhost/extract"
$CONNECT_TO = "pdf-extactext.universidad.localhost:443:127.0.0.1:443"

$STRESS_DIR = $PSScriptRoot
$PDF_PATH = Join-Path $STRESS_DIR "pdfs\documento_${PdfPages}_paginas.pdf"
$RESULTS_DIR = Join-Path $STRESS_DIR "results"
$RUN_PREFIX = "vegeta-${PdfPages}-$(Get-Date -Format 'yyyyMMdd-HHmmssfff')"
$TARGETS = Join-Path $RESULTS_DIR "$RUN_PREFIX-targets.txt"
$BIN_OUTPUT = Join-Path $RESULTS_DIR "$RUN_PREFIX.bin"
$JSON_OUTPUT = Join-Path $RESULTS_DIR "$RUN_PREFIX.json"
$PLOT_OUTPUT = Join-Path $RESULTS_DIR "$RUN_PREFIX.html"

if (-not (Test-Path -LiteralPath $PDF_PATH -PathType Leaf)) {
    throw "Falta el PDF real de $PdfPages paginas: $PDF_PATH"
}

$VEGETA_COMMAND = Get-Command vegeta -CommandType Application -ErrorAction SilentlyContinue
if ($VEGETA_COMMAND) {
    $VEGETA = $VEGETA_COMMAND.Source
}
elseif (Test-Path -LiteralPath "D:\herramientas\vegeta\vegeta.exe" -PathType Leaf) {
    $VEGETA = "D:\herramientas\vegeta\vegeta.exe"
}
else {
    throw "Vegeta no esta disponible en PATH ni en D:\herramientas\vegeta\vegeta.exe."
}

New-Item -ItemType Directory -Path $RESULTS_DIR -Force | Out-Null
$PDF_ABSOLUTE_PATH = (Resolve-Path -LiteralPath $PDF_PATH).Path

$TARGET_CONTENT = @"
POST $ENDPOINT
Content-Type: application/pdf
@$PDF_ABSOLUTE_PATH
"@
[System.IO.File]::WriteAllText($TARGETS, $TARGET_CONTENT, (New-Object System.Text.UTF8Encoding($false)))

$ATTACK_ARGUMENTS = @(
    "attack",
    "-insecure",
    "-connect-to=$CONNECT_TO",
    "-rate=$RATE",
    "-duration=$DURATION",
    "-targets=$TARGETS",
    "-output=$BIN_OUTPUT"
)
& $VEGETA @ATTACK_ARGUMENTS
if ($LASTEXITCODE -ne 0) {
    throw "vegeta attack finalizo con codigo $LASTEXITCODE."
}

& $VEGETA report -type=json "-output=$JSON_OUTPUT" $BIN_OUTPUT
if ($LASTEXITCODE -ne 0) {
    throw "vegeta report no pudo generar $JSON_OUTPUT."
}

& $VEGETA plot $BIN_OUTPUT | Set-Content -LiteralPath $PLOT_OUTPUT -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    throw "vegeta plot no pudo generar $PLOT_OUTPUT."
}

$REPORT = Get-Content -LiteralPath $JSON_OUTPUT -Raw -Encoding utf8 | ConvertFrom-Json
$REQUESTS = [int]$REPORT.requests
$STATUS_200 = [int]$REPORT.status_codes.'200'
$ERRORS = @($REPORT.errors | Where-Object { $_ })
if ($REQUESTS -le 0 -or $STATUS_200 -ne $REQUESTS -or $ERRORS.Count -gt 0) {
    Write-Host "Reporte de errores ($JSON_OUTPUT):"
    Get-Content -LiteralPath $JSON_OUTPUT -Raw -Encoding utf8 | Write-Host
    throw "Vegeta registro $REQUESTS peticiones, pero solo $STATUS_200 respuestas HTTP 200."
}

& $VEGETA report $BIN_OUTPUT
if ($LASTEXITCODE -ne 0) {
    throw "vegeta report no pudo leer $BIN_OUTPUT."
}

Write-Host "Validacion correcta: $STATUS_200 de $REQUESTS peticiones respondieron HTTP 200."
Write-Host "Binario: $BIN_OUTPUT"
Write-Host "JSON: $JSON_OUTPUT"
Write-Host "HTML: $PLOT_OUTPUT"
