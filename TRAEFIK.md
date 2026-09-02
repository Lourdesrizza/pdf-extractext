# Traefik en desarrollo local

El proyecto usa Traefik como proxy inverso para exponer la API por HTTPS sin
publicar el puerto interno `8000`. Esta configuración está pensada únicamente
para desarrollo en cada equipo: los puertos 80 y 443 se enlazan a `localhost`.

## Requisitos

1. Instalar y abrir [Docker Desktop](https://www.docker.com/products/docker-desktop/).
   En Windows, dejar habilitado el motor de contenedores Linux.
2. Confirmar desde una terminal en la raíz del repositorio:

   ```powershell
   docker --version
   docker compose version
   ```

3. Crear el archivo de variables local a partir del ejemplo:

   ```powershell
   Copy-Item .env.example .env
   ```

   Cada integrante debe cambiar `SECRET_KEY` en su propio `.env`. Ese archivo
   no se sube al repositorio.

## Inicio

Construir la imagen de la API y levantar todo el stack:

```powershell
docker build -t pdf-extactext:0.1.0 .
docker compose up -d
```

La primera ejecución descarga las imágenes de MongoDB y Traefik. No se requiere
editar el archivo `hosts`: los dominios que terminan en `.localhost` apuntan a
la propia máquina en los navegadores modernos.

## Verificación

1. Revisar que los tres servicios estén activos:

   ```powershell
   docker compose ps
   ```

   Deben figurar `traefik`, `app` y `basededatos`; los dos últimos pueden tardar
   unos segundos mientras MongoDB completa su health check.

2. Abrir en el navegador:

   - API y documentación: <https://pdf-extactext.universidad.localhost/docs>
   - Salud de la API: <https://pdf-extactext.universidad.localhost/health>
   - Panel de rutas: <https://traefik.universidad.localhost/dashboard/>

3. Alternativamente, comprobar la salud desde PowerShell (la opción `-k`
   acepta el certificado local autofirmado):

   ```powershell
   curl.exe -k https://pdf-extactext.universidad.localhost/health
   ```

Traefik genera un certificado local autofirmado. La primera vez el navegador
mostrará una advertencia de seguridad; es esperable en desarrollo local y debe
aceptarse solo si la URL termina en `.localhost` y se está trabajando en la
máquina propia.

## Diagnóstico y apagado

```powershell
docker compose logs -f traefik
docker compose logs -f app
docker compose down
```

Si el puerto 80 o 443 está ocupado, identificá y detené el proceso que lo usa,
o cambiá el mapeo de puertos de `traefik` en `docker-compose.yml`. No expongas
el panel de Traefik a una red pública sin agregar autenticación.
