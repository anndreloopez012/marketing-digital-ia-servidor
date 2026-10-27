# Montar el backend de Campuslands Marketing IA — guía para la IA

Eres la IA (Claude Code, Codex o Antigravity) que monta el backend en el servidor de una empresa. El sistema son dos
piezas: la app (se instala en cada PC, con la IA) y este backend (la base de datos y todo lo que el sistema guarda).
La persona te dio este repositorio y te pidió que instales y configures todo. Sigue los pasos en orden; cada uno se puede repetir. Habla con
la persona en español, sin jerga, y pregúntale solo lo que no puedes saber.

## Reglas firmes
- **Nunca pidas, copies ni muestres contraseñas, tokens ni la clave del administrador.** `montar.py` genera la clave
  de la base y la guarda en `.env` (solo para el dueño). La clave del primer administrador la lee la persona con el
  comando que da `montar.py admin`.
- No borres volúmenes, respaldos ni `.env`. Si algo se ve roto, explícalo y pregunta antes de tocarlo.
- Las IA no se instalan en el servidor: cada persona las usa desde su equipo con su plan.

## 1. Diagnóstico
```bash
python3 montar.py diagnostico
```
Si falta Docker (con Compose v2) o git, instálalos con el método oficial del sistema (en Ubuntu/Debian:
https://docs.docker.com/engine/install/ubuntu/) y vuelve a correr el diagnóstico.

## 2. Preguntas a la persona
1. **El dominio** donde vivirá la app (por ejemplo `marketing.tuempresa.com`).
2. **El correo del administrador** (avisos de HTTPS y primer usuario).
3. **¿Ya tienen un PostgreSQL?** Si sí, que te dé la dirección completa `postgresql://usuario:clave@servidor:5432/base`
   o, mejor, que la ponga ella en `--base` al correr el comando. Si no, se crea una propia en un contenedor.
4. **La versión** de la app (por omisión `main`; una etiqueta como `v1.0.0` si la tienen).

## 3. Configurar
```bash
python3 montar.py configurar --dominio marketing.tuempresa.com --correo admin@tuempresa.com
# con base existente:  … --base 'postgresql://…'
```
Luego pide a la persona que apunte el **DNS** del dominio (registro A) a la IP pública de este servidor y que abra los
puertos **80 y 443**. Comprueba con `getent hosts marketing.tuempresa.com` (o `nslookup`) antes de seguir.

## 4. Traer la app y encender
```bash
python3 montar.py traer
python3 montar.py arrancar
python3 montar.py verificar
```
Si `traer` falla por permisos, el repositorio de la app es privado: que la persona inicie sesión en GitHub en este
servidor (`gh auth login`) o use una llave de despliegue, y repite. Si `verificar` falla, mira
`docker compose logs app caddy` y explica lo que veas.

## 5. Primer administrador
```bash
python3 montar.py admin
```
Dale a la persona el comando que imprime para que **ella** lea la clave. Con esa clave entra desde la app de su PC
(paso 6), la cambia en Ajustes → Mi cuenta y crea a su equipo en Administración → Usuarios (rol y marcas de cada
quien).

## 6. Cada PC de la empresa
La app se instala en cada PC con su propia guía (`INSTALAR-CON-IA.md` del repo de la app). En la instalación se pone la
URL de este servidor y el usuario de la persona:
```bash
python scripts/instalar.py conexion --url https://marketing.tuempresa.com --usuario nombre@empresa.com
```
Al abrir la app, la persona escribe su contraseña. Su IA, sus vaults y sus agentes se quedan en su PC; lo que hace
queda guardado aquí. En Ajustes → Equipos, quien administra marca la PC que hace los trabajos automáticos con IA
(vigilancias, informes).

## 7. Respaldos y actualizaciones
- Con base propia hay un respaldo diario automático en `./respaldos` (se guardan 14 días; `DIAS_DE_RESPALDO` en
  `.env`). `python3 montar.py respaldar` hace uno ahora. Recomienda copiar `./respaldos` fuera del servidor.
- Si venían de una instalación local con datos: copia su carpeta `data` al volumen y corre
  `docker compose exec app python scripts/instalar.py datos --migrar` (copia, no borra).
- Actualizar: `python3 montar.py actualizar --version v1.2.0` (las migraciones de la base corren solas al arrancar).

## 8. Cierre
Resume a la persona: la dirección, quién es el administrador, dónde están los respaldos, cómo conecta cada equipo y
qué quedó pendiente (DNS, puertos, base externa).
