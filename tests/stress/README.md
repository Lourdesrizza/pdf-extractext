# Pruebas de rendimiento de extracción PDF

k6 ejecuta pruebas de carga programables en JavaScript. Vegeta envía tráfico
HTTP desde targets de texto y genera reportes. El benchmark mide una única
extracción contra el límite de 440 ms; el spike observa el comportamiento al
subir, mantener y reducir 100 usuarios concurrentes, sin imponerle ese límite.

## Preparación

1. Colocar el PDF real en
   `tests/stress/pdfs/documento_279_paginas.pdf`. Los scripts fallan si falta y
   nunca generan un reemplazo.
2. Comprobar que tiene exactamente 279 páginas:

   ```powershell
   uv run python -c "import pymupdf; print(pymupdf.open(r'tests/stress/pdfs/documento_279_paginas.pdf').page_count)"
   ```

3. Construir y levantar el proyecto:

   ```powershell
   docker build -t pdf-extactext:0.1.0 .
   docker compose up -d
   ```

Las pruebas usan el hostname real configurado en Traefik:
`https://pdf-extactext.universidad.localhost/extract`. Los scripts aceptan el
certificado autofirmado únicamente para este entorno local.

## k6

Benchmark de una iteración y un VU:

```powershell
k6 run tests/stress/benchmark_279.js
```

`pdf_279_duration` mide `response.timings.duration`. El resultado es PASS si
`max < 440 ms`; con 440 ms o más el threshold falla. No hay tiempos
predefinidos ni resultados simulados.

Spike de 100 VUs:

```powershell
k6 run tests/stress/spike_tests.js
k6 run --out web-dashboard tests/stress/spike_tests.js
```

El resumen muestra `avg`, `min`, `med`, `p90`, `p95` y `max`. Para usar el Web
Dashboard actual y exportar HTML en PowerShell:

```powershell
$env:K6_WEB_DASHBOARD="true"
k6 run tests/stress/spike_tests.js

$env:K6_WEB_DASHBOARD="true"
$env:K6_WEB_DASHBOARD_EXPORT="tests/stress/results/k6-report.html"
k6 run tests/stress/spike_tests.js
```

## Vegeta

Los scripts resuelven la ruta absoluta del mismo PDF y generan el target
temporal automáticamente. La carga inicial es moderada: 1 request/segundo
durante 10 segundos. `RATE`, `DURATION`, `TARGETS`, `BIN_OUTPUT`, `JSON_OUTPUT`
y `PLOT_OUTPUT` están agrupados al inicio de cada script para facilitar cambios.

```powershell
.\tests\stress\run_vegeta.ps1
```

```bash
./tests/stress/run_vegeta.sh
```

Los resultados quedan en `tests/stress/results/` como
`vegeta-results.bin`, `vegeta-results.json` y `vegeta-plot.html`; los archivos
generados no se versionan.
