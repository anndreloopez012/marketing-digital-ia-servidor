#!/usr/bin/env python3
"""Monta Campuslands Marketing IA en un servidor (lo conduce una IA siguiendo INSTALAR-CON-IA.md).

Cada paso se puede repetir y responde en texto o en JSON (--json):

  diagnostico                 qué hay en el servidor (Docker, Compose, git, puertos) y qué falta
  configurar --dominio D --correo C [--base postgresql://…] [--version vX] [--repo URL] [--puertos 80,443]
                              escribe .env (solo para el dueño). Sin --base, PostgreSQL va en un contenedor con una clave
                              nueva que no se cambia al repetir; con --base usa esa base (la de la empresa).
  traer                       trae a ./app la versión de la app que dice .env (git clone/fetch)
  arrancar                    construye y enciende todo (docker compose up -d --build)
  verificar                   que la app responda por HTTPS en el dominio
  admin                       cómo ver la clave del primer administrador (la lee la persona; nunca se imprime aquí)
  respaldar                   copia ahora la base a ./respaldos (además del respaldo diario automático)
  actualizar --version vX     trae esa versión y vuelve a arrancar (las migraciones corren solas)
  apagar                      detiene los contenedores (los datos quedan en sus volúmenes)

Solo usa la biblioteca estándar. Nunca pide ni muestra contraseñas.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(os.environ.get("MONTAR_RAIZ") or Path(__file__).resolve().parent)
ENV = RAIZ / ".env"
APP = RAIZ / "app"
APP_REPO = "https://github.com/anndreloopez012/marketing-digital-ia.git"
APP_VERSION = "main"
_DOMINIO = re.compile(r"^(localhost|(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})$")
_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def salida(datos, como_json: bool, texto: str) -> None:
    print(json.dumps(datos, ensure_ascii=False, indent=2) if como_json else texto)


# ── .env ────────────────────────────────────────────────────────────────────────
def leer_env(ruta: Path = ENV) -> dict:
    datos = {}
    try:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return datos


def _escribir_env(ruta: Path, datos: dict) -> None:
    texto = "# Lo escribe montar.py configurar. Tiene secretos: no lo subas ni lo compartas.\n" + "".join(f"{k}={v}\n" for k, v in datos.items())
    temporal = ruta.with_name(ruta.name + ".tmp")
    fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(texto)
    os.replace(temporal, ruta)
    os.chmod(ruta, 0o600)


def configurar_env(ruta: Path, dominio: str, correo: str, base: str = "", version: str = "", repo: str = "",
                   puertos: tuple[int, int] = (80, 443)) -> dict:
    dominio = (dominio or "").strip().lower()
    if not _DOMINIO.match(dominio):
        raise ValueError("El dominio va sin https:// ni rutas, por ejemplo marketing.tuempresa.com")
    if not _CORREO.match((correo or "").strip()):
        raise ValueError("El correo del administrador no es válido")
    base = (base or "").strip()
    if base and not base.startswith(("postgresql://", "postgres://")):
        raise ValueError("La base externa debe ser una dirección postgresql://usuario:clave@servidor:5432/base")
    http, https = (int(p) for p in puertos)
    previo = leer_env(ruta)
    clave = previo.get("POSTGRES_PASSWORD") or secrets.token_urlsafe(32)   # nunca cambia al repetir: la base ya la usa
    datos = {"DOMINIO": dominio, "CORREO_ADMIN": correo.strip(), "BASE": "externa" if base else "propia",
             "POSTGRES_PASSWORD": clave,
             "DATABASE_URL": base or f"postgresql://marketing:{clave}@db:5432/marketing_ia",
             "APP_REPO": repo or previo.get("APP_REPO") or APP_REPO,
             "APP_VERSION": version or previo.get("APP_VERSION") or APP_VERSION,
             "PUERTO_HTTP": str(http), "PUERTO_HTTPS": str(https),
             "PUERTO_HTTPS_PUBLICO": "" if https == 443 else f":{https}",
             "DIAS_DE_RESPALDO": previo.get("DIAS_DE_RESPALDO") or "14"}
    _escribir_env(ruta, datos)
    return datos


def compose_base(env: dict) -> list[str]:
    return ["docker", "compose"] + (["--profile", "base-propia"] if env.get("BASE") != "externa" else [])


def url_salud(env: dict) -> str:
    return f"https://{env['DOMINIO']}{env.get('PUERTO_HTTPS_PUBLICO') or ''}/api/health"


def _correr(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=RAIZ, text=True, **kw)


# ── pasos ───────────────────────────────────────────────────────────────────────
def diagnostico(args) -> int:
    docker = bool(shutil.which("docker"))
    compose = docker and _correr(["docker", "compose", "version"], capture_output=True).returncode == 0
    activo = docker and _correr(["docker", "info"], capture_output=True).returncode == 0
    env = leer_env()
    d = {"docker": docker, "docker_activo": activo, "compose": compose, "git": bool(shutil.which("git")),
         "configurado": bool(env.get("DOMINIO")), "dominio": env.get("DOMINIO", ""), "base": env.get("BASE", ""),
         "app": (APP / "app.py").is_file(), "version": env.get("APP_VERSION", "")}
    pendiente = []
    if not docker or not compose:
        pendiente.append("instalar Docker con Compose v2 (https://docs.docker.com/engine/install/)")
    elif not activo:
        pendiente.append("encender Docker")
    if not d["git"]:
        pendiente.append("instalar git")
    if not d["configurado"]:
        pendiente.append("configurar --dominio … --correo …")
    if not d["app"]:
        pendiente.append("traer")
    d["pendiente"] = pendiente
    salida(d, args.json, "\n".join([f"Docker: {'sí' if docker else 'no'} · Compose: {'sí' if compose else 'no'} · git: {'sí' if d['git'] else 'no'}",
                                    f"Dominio: {d['dominio'] or '—'} · Base: {d['base'] or '—'} · App: {d['version'] if d['app'] else 'sin traer'}",
                                    "Falta: " + ("; ".join(pendiente) if pendiente else "nada")]))
    return 0


def configurar(args) -> int:
    puertos = tuple(int(p) for p in (args.puertos or "80,443").split(","))
    try:
        env = configurar_env(ENV, args.dominio, args.correo, base=args.base or "", version=args.version or "",
                             repo=args.repo or "", puertos=puertos)
    except ValueError as error:
        salida({"error": str(error)}, args.json, str(error)); return 1
    d = {"dominio": env["DOMINIO"], "base": env["BASE"], "version": env["APP_VERSION"], "env": str(ENV)}
    salida(d, args.json, f"Listo: .env para {env['DOMINIO']} (base {env['BASE']}, versión {env['APP_VERSION']}). "
           "Apunta el DNS del dominio a este servidor y sigue con: traer, arrancar.")
    return 0


def _env_o_error(args) -> dict | None:
    env = leer_env()
    if not env.get("DOMINIO"):
        salida({"error": "Falta configurar: montar.py configurar --dominio … --correo …"}, args.json,
               "Falta configurar: montar.py configurar --dominio … --correo …")
        return None
    return env


def traer(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    version = env.get("APP_VERSION") or APP_VERSION
    if (APP / ".git").is_dir():
        pasos = [["git", "-C", str(APP), "fetch", "--depth", "1", "origin", version], ["git", "-C", str(APP), "checkout", "-q", "FETCH_HEAD"]]
    else:
        pasos = [["git", "clone", "-q", "--depth", "1", "--branch", version, env.get("APP_REPO") or APP_REPO, str(APP)]]
    for cmd in pasos:
        r = _correr(cmd, capture_output=True)
        if r.returncode != 0:
            msg = f"No se pudo traer la app ({version}): {r.stderr.strip()[-400:]}"
            salida({"error": msg}, args.json, msg); return 1
    commit = _correr(["git", "-C", str(APP), "rev-parse", "--short", "HEAD"], capture_output=True).stdout.strip()
    salida({"version": version, "commit": commit}, args.json, f"App {version} ({commit}) lista en ./app.")
    return 0


def arrancar(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    if not (APP / "app.py").is_file():
        salida({"error": "Falta traer la app: montar.py traer"}, args.json, "Falta traer la app: montar.py traer"); return 1
    (RAIZ / "respaldos").mkdir(exist_ok=True)
    r = _correr(compose_base(env) + ["up", "-d", "--build"])
    if r.returncode != 0:
        salida({"error": "docker compose up falló: revisa el mensaje de arriba"}, args.json, "docker compose up falló: revisa el mensaje de arriba")
        return 1
    salida({"ok": True}, args.json, "Encendido. Sigue con: verificar.")
    return 0


def verificar(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    url = url_salud(env)
    contexto = ssl._create_unverified_context() if env["DOMINIO"] == "localhost" else None   # localhost: certificado local de Caddy
    fin, ultimo = time.time() + float(args.esperar), ""
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10, context=contexto) as r:
                datos = json.loads(r.read() or b"{}")
            salida({"ok": True, "url": url, "salud": datos}, args.json, f"La app responde en {url}.")
            return 0
        except Exception as error:   # noqa: BLE001 — se informa tal cual
            ultimo = str(error)
        if time.time() >= fin:
            break
        time.sleep(3)
    msg = (f"La app no responde en {url}: {ultimo}. Revisa que el DNS apunte aquí, que los puertos 80 y 443 estén "
           "abiertos y «docker compose logs app caddy».")
    salida({"ok": False, "url": url, "error": msg}, args.json, msg)
    return 1


def admin(args) -> int:
    cmd = "docker compose exec app cat /datos/bootstrap-admin.txt"
    salida({"comando": cmd}, args.json, f"La clave del primer administrador la ve solo la persona: {cmd}\n"
           "Que entre con ella, la cambie en Ajustes → Mi cuenta y cree a su equipo en Administración → Usuarios.")
    return 0


def respaldar(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    if env.get("BASE") == "externa":
        msg = "La base es externa: su respaldo es el de la empresa (aquí no se toca)."
        salida({"ok": False, "error": msg}, args.json, msg); return 1
    (RAIZ / "respaldos").mkdir(exist_ok=True)
    destino = RAIZ / "respaldos" / f"base-{datetime.now():%Y-%m-%d-%H%M%S}.sql"
    with open(destino, "w", encoding="utf-8") as fh:
        r = _correr(compose_base(env) + ["exec", "-T", "db", "pg_dump", "-U", "marketing", "marketing_ia"], stdout=fh)
    if r.returncode != 0:
        destino.unlink(missing_ok=True)
        salida({"ok": False, "error": "pg_dump falló"}, args.json, "pg_dump falló: ¿está encendida la base?"); return 1
    salida({"ok": True, "archivo": str(destino)}, args.json, f"Respaldo en {destino}.")
    return 0


def actualizar(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    env["APP_VERSION"] = args.version
    _escribir_env(ENV, env)
    return traer(args) or arrancar(args)


def apagar(args) -> int:
    env = _env_o_error(args)
    if env is None:
        return 1
    r = _correr(compose_base(env) + ["stop"])
    salida({"ok": r.returncode == 0}, args.json, "Detenido (los datos quedan en sus volúmenes)." if r.returncode == 0 else "No se pudo detener.")
    return 0 if r.returncode == 0 else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="montar.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="paso", required=True)
    pasos = {"diagnostico": diagnostico, "configurar": configurar, "traer": traer, "arrancar": arrancar, "verificar": verificar,
             "admin": admin, "respaldar": respaldar, "actualizar": actualizar, "apagar": apagar}
    for nombre in pasos:
        s = sub.add_parser(nombre); s.add_argument("--json", action="store_true", help="salida en JSON")
        if nombre == "configurar":
            s.add_argument("--dominio", required=True); s.add_argument("--correo", required=True)
            s.add_argument("--base", help="postgresql://… de una base existente (si no, una propia en un contenedor)")
            s.add_argument("--version", help=f"rama o etiqueta de la app (por omisión {APP_VERSION})")
            s.add_argument("--repo", help="otro repositorio de la app")
            s.add_argument("--puertos", help="HTTP,HTTPS (por omisión 80,443)")
        if nombre == "actualizar":
            s.add_argument("--version", required=True)
        if nombre == "verificar":
            s.add_argument("--esperar", default="120", help="segundos que espera a que responda")
    args = p.parse_args(argv)
    return pasos[args.paso](args)


if __name__ == "__main__":
    sys.exit(main())
