# El backend — diseño

Fecha: 27 oct 2026. El sistema son dos piezas: la app (se instala en cada PC con la IA, los vaults y los agentes) y el
backend (este repositorio: la base de datos y todo lo que el sistema guarda, en el servidor de la empresa).

## Lo que se quiere
- Montar el servidor de una empresa **dando el nombre de este repositorio a una IA** y pidiéndole que instale y
  configure todo (`INSTALAR-CON-IA.md`).
- Elegir el backend por dominio: cada empresa tiene su servidor; cada PC lo pone al instalar la app
  (`instalar.py conexion --url https://… --usuario …`) y la persona entra con su contraseña.
- PostgreSQL propio en un contenedor (con clave generada) o la base que ya tenga la empresa (`--base postgresql://…`).
- HTTPS sin pasos manuales y respaldo diario.

## Piezas
| Pieza | Decisión |
|---|---|
| Repo aparte | Este repo no copia código de la app: `montar.py traer` la clona en `./app` a la versión de `.env`. Así actualizar es cambiar de etiqueta. |
| `docker-compose.yml` | `app` (modo servidor, documentos en la base, cuentas obligatorias), `caddy` (HTTPS automático, sin búfer para el canal en vivo y los agentes), y con perfil `base-propia`: `db` (PostgreSQL 16) y `respaldo` (pg_dump diario, 14 días). |
| `Dockerfile` | Python 3.12 slim + `psycopg[binary]` + FFmpeg; usuario sin privilegios; datos en el volumen `/datos`. |
| `montar.py` | Solo biblioteca estándar, pasos repetibles con `--json` para que una IA los lea: diagnostico, configurar, traer, arrancar, verificar, admin, respaldar, actualizar, apagar. |
| `.env` | Lo escribe `configurar` con permisos 600; la clave de la base no cambia al repetir. Nunca se sube. |

## Reglas
- Ningún paso imprime contraseñas ni tokens; la clave del primer administrador la lee la persona con el comando que da
  `admin`.
- Nada borra volúmenes ni respaldos.
- `MARKETING_IA_MODO=servidor` exige `AUTH_REQUIRED=1` y `MARKETING_IA_URL_PUBLICA=https://…`: la app no arranca sin
  ellos (los pone el compose).

## Fuera de alcance
- El editor de video corre en la app de cada PC, no en el backend.
- Varios procesos de la app detrás de un balanceador (la cola de encargos vive en memoria de un proceso).

## Pruebas
- `tests/test_montar.py`: `.env` (permisos, secretos que no cambian, validación), perfiles, CLI sin Docker.
- De punta a punta en un equipo con Docker: `configurar --dominio localhost --puertos 8080,8443`, `traer`, `arrancar`,
  `verificar` contra la app real con PostgreSQL.
