# DOCS_DOCKER.md — `docker save` & `docker load`

Cubre el Issue #12. Sirve para **distribuir imágenes Docker sin un registry**:
útil en entornos air-gapped, servidores sin internet o para congelar una
versión exacta de la imagen en un artefacto.

---

## Tabla de contenidos

1. [`docker save` — exportar una imagen a un archivo `.tar`](#docker-save--exportar-una-imagen-a-un-archivo-tar)
2. [`docker load` — restaurar una imagen desde un `.tar`](#docker-load--restaurar-una-imagen-desde-un-tar)
3. [Flujo completo: de una PC a otra](#flujo-completo-de-una-pc-a-otra)
4. [Comprimir el `.tar` para achicar la transferencia](#comprimir-el-tar-para-achicar-la-transferencia)
5. [Verificación de integridad](#verificación-de-integridad)
6. [Pitfalls comunes](#pitfalls-comunes)

---

## `docker save` — exportar una imagen a un archivo `.tar`

`docker save` toma **una o varias imágenes Docker** desde tu daemon local y
las empaqueta en un archivo `.tar` que se puede mover como cualquier otro.

### Sintaxis

```bash
docker save [OPTIONS] IMAGE [IMAGE...]
# Options:
#   -o, --output string   Escribir a un archivo en vez de stdout
#       --plain           Omitir metadata de progreso (útil en pipelines)
```

### Ejemplo 1 — Imagen única

```bash
# Construir/taggear la imagen del proyecto
 docker build -t pdf-extactext:0.1.0 .

# Exportar a un .tar
docker save -o pdf-extactext-0.1.0.tar pdf-extactext:0.1.0

ls -lh pdf-extactext-0.1.0.tar
# -rw------- 1 user group 180M Jul 22 10:00 pdf-extactext-0.1.0.tar
```

### Ejemplo 2 — Varias imágenes en un mismo archivo

```bash
docker save \
  -o stack-offline.tar \
  pdf-extactext:0.1.0 \
  mongo:7
```

### Ejemplo 3 — Salida por stdout + compresión en una sola línea

```bash
docker save pdf-extactext:0.1.0 | gzip > pdf-extactext-0.1.0.tar.gz
```

---

## `docker load` — restaurar una imagen desde un `.tar`

`docker load` lee un `.tar` producido por `docker save` y carga las imágenes
que contiene en el daemon local.

### Sintaxis

```bash
docker load [OPTIONS]
# Options:
#   -i, --input string   Leer desde un archivo en vez de stdin
#   -q, --quiet          Suprimir el progreso
```

### Ejemplo 1 — Cargar desde un archivo

```bash
docker load -i pdf-extactext-0.1.0.tar
# Loaded image: pdf-extactext:0.1.0

docker images | grep pdf-extactext
# pdf-extactext   0.1.0   6f5b3a2c1d4e   2 minutes ago   180MB
```

### Ejemplo 2 — Cargar un `.tar.gz` comprimido directamente

```bash
docker load -i pdf-extactext-0.1.0.tar.gz
# o equivalevente con stdin + gunzip:
gunzip -c pdf-extactext-0.1.0.tar.gz | docker load
```

### Ejemplo 3 — Levantar el stack con la imagen recién cargada

```bash
# 1) Cargar la API
docker load -i pdf-extactext-0.1.0.tar

# 2) Cargar MongoDB (si nunca se descargó)
docker load -i stack-offline.tar

# 3) Levantar el stack del proyecto (docker-compose.yml usa image: pdf-extactext:0.1.0)
docker compose up -d
```

---

## Flujo completo: de una PC a otra

```text
[ PC A ]                          [ PC B ]
docker build -t app:0.1.0 .       docker load -i app-0.1.0.tar
docker save -o app-0.1.0.tar app:0.1.0   docker images
docker images                     docker compose up -d
   |                                        ^
   +----- scp / pendrive ------------------+
```

```bash
# En PC A (con internet)
docker build -t pdf-extactext:0.1.0 .
docker save -o pdf-extactext-0.1.0.tar pdf-extactext:0.1.0
gzip pdf-extactext-0.1.0.tar        # opcional pero recomendado

# Transferir el archivo a la PC B (sin internet)
scp pdf-extactext-0.1.0.tar.gz user@srv-prod:/opt/images/

# En PC B (air-gapped)
gunzip pdf-extactext-0.1.0.tar.gz
docker load -i pdf-extactext-0.1.0.tar
docker compose up -d                 # el compose usa image: pdf-extactext:0.1.0
```

---

## Comprimir el `.tar` para achicar la transferencia

| Comando | Tamaño aprox. | Tiempo |
|---|---|---|
| `docker save -o app.tar app:0.1.0` | 100% | rápido |
| `docker save app:0.1.0 \| gzip > app.tar.gz` | ~35% | lento |
| `docker save app:0.1.0 \| xz -T 0 > app.tar.xz` | ~28% | muy lento |

Para máxima compresión multihilo:

```bash
docker save pdf-extactext:0.1.0 | xz -T 0 -9 > pdf-extactext-0.1.0.tar.xz
```

Carga equivalente (Docker detecta gzip/bzip2/xz automáticamente):

```bash
docker load -i pdf-extactext-0.1.0.tar.xz
```

---

## Verificación de integridad

```bash
# Generar checksum en la PC de origen
sha256sum pdf-extactext-0.1.0.tar > pdf-extactext-0.1.0.tar.sha256

# Verificar luego de la transferencia
sha256sum -c pdf-extactext-0.1.0.tar.sha256
# pdf-extactext-0.1.0.tar: OK
```

Solo después de que se confirme el checksum conviene ejecutar `docker load`.

---

## Pitfalls comunes

| Problema | Causa | Solución |
|---|---|---|
| `Error: processing tar file(...): write /app: no space left on device` | Disco lleno en destino | Limpiar imágenes con `docker image prune -a` |
| `archive/tar: invalid tar header` | `.tar` corrupto por transferencia | Recalcular `sha256sum` y volver a copiar |
| `docker save` exporta tags sueltos | Se hizo `save` solo de la imagen sin repo | Hacer `save pdf-extactext:0.1.0`, no solo `0.1.0` |
| La imagen no aparece con `docker images` luego de `load` | Se cargó como `sha256:...` sin tag | Re-taggear con `docker tag <sha> pdf-extactext:0.1.0` |
| `compose` reconstruye la imagen en lugar de usar la cargada | Quedó `build:` en el `docker-compose.yml` | Asegurarse de tener `image:` sin `build:` (ver Issue #10) |

---

## Resumen

| Comando | Para qué |
|---|---|
| `docker save -o X.tar IMAGEN[:TAG]` | Exportar una imagen local a un archivo `.tar`. |
| `docker load -i X.tar` | Importar imágenes desde un `.tar` al daemon local. |
| *pipe* / `-o` / gzip | Permite comprimir la transferencia sin pasos extra. |

> 💡 **Insider tip**: `docker save` trabaja con **imágenes**, mientras que
> `docker export` trabaja con **contenedores en ejecución**. Para distribuir
> artefactos reproducibles debes usar `docker save`.
