# Pruebas de rendimiento de extracción PDF

k6 ejecuta pruebas de carga programables en JavaScript. Vegeta envía tráfico
HTTP desde targets de texto y genera reportes. El benchmark mide una única
extracción contra el límite de 440 ms; el spike observa el comportamiento al
subir, mantener y reducir 100 usuarios concurrentes, sin imponerle ese límite.

## Preparación

Para la prueba funcional del documento oficial de 90 páginas, colocar el PDF
proporcionado por el profesor en
`tests/stress/pdfs/documento_90_paginas.pdf`. Comprobar las páginas con:

```powershell
uv run --isolated --locked python -c "import pymupdf; print(pymupdf.open(r'tests/stress/pdfs/documento_90_paginas.pdf').page_count)"
```

El archivo PDF y los reportes generados están ignorados por Git y no se
versionan.

Para el benchmark de 279 páginas, colocar el PDF real en
`tests/stress/pdfs/documento_279_paginas.pdf`. Los scripts fallan si falta y
nunca generan un reemplazo.
Comprobar que tiene exactamente 279 páginas:

   ```powershell
   uv run python -c "import pymupdf; print(pymupdf.open(r'tests/stress/pdfs/documento_279_paginas.pdf').page_count)"
   ```

`/extract` acepta cuerpos PDF de hasta 20 MiB (20.971.520 bytes) y devuelve
HTTP 413 si se supera ese límite. El PDF real de 279 páginas (17.749.468 bytes)
cabe en ese endpoint. `/api/v1/upload` conserva su límite independiente de
5 MiB; este benchmark no persiste documentos.

Construir y levantar el proyecto:

   ```powershell
   docker build -t pdf-extactext:0.1.0 .
   docker compose up -d
   ```

Las pruebas usan el hostname real configurado en Traefik:
`https://pdf-extactext.universidad.localhost/extract`. Cada script lo mapea con
la opción `hosts` de k6 a `127.0.0.1`, manteniendo ese hostname en la petición
para que coincida con la regla de Traefik. Los scripts aceptan el certificado
autofirmado únicamente para este entorno local.

## k6

Smoke test funcional del PDF oficial de 90 páginas, con una petición. Verifica
HTTP 200 y muestra la duración real; no aplica un límite de tiempo:

```powershell
k6 run tests/stress/smoke_90.js
```

El threshold `checks: rate==1` hace fallar k6 si la respuesta no es HTTP 200.
La métrica `pdf_90_duration` y el log muestran la duración medida. Un check
aprobado confirma la funcionalidad; una duración alta indica lentitud, no un
fallo funcional. Se puede cambiar el endpoint con `EXTRACT_URL`.

Dashboard para repetir la prueba del PDF de 90 páginas durante unos 45
segundos, con 1 VU y una pausa de 5 segundos entre peticiones. En una consola
PowerShell:

```powershell
$env:K6_WEB_DASHBOARD = "true"
$env:K6_WEB_DASHBOARD_EXPORT = "tests/stress/results/dashboard-90.html"
try {
    k6 run tests/stress/dashboard_90.js
}
finally {
    Remove-Item Env:K6_WEB_DASHBOARD -ErrorAction SilentlyContinue
    Remove-Item Env:K6_WEB_DASHBOARD_EXPORT -ErrorAction SilentlyContinue
}
```

Mientras k6 está ejecutándose, abrí `http://localhost:5665` en el navegador
para ver las métricas en vivo. Al terminar, el HTML exportado queda en
`tests/stress/results/dashboard-90.html`; los reportes de esta carpeta están
ignorados por Git. Para abrir el reporte exportado desde PowerShell:

```powershell
Start-Process .\tests\stress\results\dashboard-90.html
```

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

En PowerShell, `run_vegeta.ps1` usa por defecto el PDF real de 279 páginas;
para probar el de 90 páginas hay que elegirlo explícitamente. Si falta el PDF
seleccionado, el script falla sin sustituirlo. Busca `vegeta` en PATH y, en
Windows, acepta también `D:\herramientas\vegeta\vegeta.exe`. Envía 1 petición
por segundo durante 10 segundos, con `-connect-to` para dirigir
`pdf-extactext.universidad.localhost:443` a `127.0.0.1:443` sin cambiar el
hostname que recibe Traefik.

```powershell
.\tests\stress\run_vegeta.ps1 -PdfPages 90

# Cuando esté disponible el PDF de 279 páginas:
.\tests\stress\run_vegeta.ps1
```

El script Bash conserva su configuración para 279 páginas:

```bash
./tests/stress/run_vegeta.sh
```

El script de PowerShell guarda el binario, el reporte JSON y el gráfico HTML en
`tests/stress/results/`, con nombres como `vegeta-90-AAAAMMDD-HHMMSSmmm.bin`,
`.json` y `.html` (o `vegeta-279-...`). La marca de tiempo conserva resultados
de corridas anteriores. Al terminar, exige al menos una petición y comprueba
en el JSON que todas respondieron HTTP 200; si falla, muestra ese reporte y
devuelve un error. Los resultados generados no se versionan.
