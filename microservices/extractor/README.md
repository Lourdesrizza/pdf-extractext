# Extractor PDF a Markdown

Microservicio independiente en Python 3.12 y FastAPI. Sus dependencias y tests
son propios; no importa código ni configuración del monolito.

## Contrato

- `GET /health`: HTTP 200, `{"status": "ok", "service": "extractor"}`.
- `POST /extract`: recibe los bytes del PDF como cuerpo `application/pdf`,
  sin formulario multipart. Devuelve HTTP 200 y `application/json`:
  `{"content": "<Markdown>", "page_count": 2}`.
- HTTP 415 si falta `Content-Type` o no es `application/pdf`.
- HTTP 400 si el cuerpo está vacío, no comienza con `%PDF`, no puede abrirse
  como PDF o requiere contraseña. Los errores tienen el campo JSON `detail`.

El cuerpo se lee en memoria y se abre con
`pymupdf.open(stream=body, filetype="pdf")`. Se obtiene `page_count` y se pasa el
documento directamente a `pymupdf4llm.to_markdown`. El documento se cierra al
terminar, incluso si ocurre un error. No se guardan PDFs ni imágenes, no se crean
archivos temporales y no hay MongoDB ni persistencia.

Se usa `use_ocr=False`, `write_images=False` y `embed_images=False`. Los PDFs
escaneados no obtienen transcripción de sus imágenes en esta etapa. El Markdown
se infiere del diseño del PDF; no es el texto plano producido por el monolito.
La versión fijada de PyMuPDF4LLM incluye PyMuPDF Layout y sus dependencias de
análisis de página. No se instala un motor de OCR.

Referencia de la API de conversión:
[PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html).

## Ejecución local

Desde la raíz del repositorio, en PowerShell, con Python 3.12 y uv:

```powershell
Set-Location microservices/extractor
uv sync --locked
uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Desde otra terminal ubicada en la raíz del repositorio:

```powershell
curl.exe http://127.0.0.1:8001/health
curl.exe --fail-with-body -X POST http://127.0.0.1:8001/extract -H "Content-Type: application/pdf" --data-binary "@pdfs/mi_documento.pdf"
```

`pdfs/mi_documento.pdf` es un PDF real disponible en el repositorio. No se usa
como fixture: los tests generan sus propios PDFs mínimos en memoria.

## Tests

Ejecutar desde `microservices/extractor`:

```powershell
uv run --locked pytest -v
```

La configuración de pytest corta la búsqueda de `conftest.py` en `tests/` para
evitar importar los fixtures de MongoDB del monolito. El comando anterior
ejecuta únicamente la suite de este microservicio.

Se cubren salud, respuesta JSON, Markdown, cantidad y orden de páginas,
cuerpo vacío, firma inválida, PDF corrupto, PDF con contraseña, tipos de contenido
incorrectos o ausentes, parámetros del tipo de contenido y PDF de imagen sin OCR.

## Docker

Construir desde la raíz del repositorio:

```powershell
docker build --tag pdf-extractor-service:0.1.0 microservices/extractor
```

Para levantarlo de forma independiente:

```powershell
docker run --rm --name pdf-extractor-service -p 127.0.0.1:8001:8000 pdf-extractor-service:0.1.0
```

El contenedor usa un usuario sin privilegios y las dependencias de ejecución
fijadas en `uv.lock`. La verificación de Docker prevista para esta etapa se
limita a construir la imagen. No se
integra con Compose, Traefik, réplicas ni patrones de resiliencia, y no se
realizan mediciones de rendimiento.
