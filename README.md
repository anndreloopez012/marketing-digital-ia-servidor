# Campuslands Marketing IA — backend

El sistema son dos piezas:

1. **La app** ([marketing-digital-ia](https://github.com/anndreloopez012/marketing-digital-ia)): se instala en cada PC
   con todas sus funciones, la IA con el plan de cada persona, sus vaults, agentes y memoria.
2. **El backend** (este repositorio): va en el servidor de la empresa con la base de datos y todo lo que el sistema
   guarda (usuarios, roles, marcas, correo, redes, publicaciones, documentos, bitácora). Publica lo programado aunque
   todas las PC estén apagadas.

Cada empresa tiene su backend con su dominio. Al instalar la app en una PC se pone la URL de este servidor y el
usuario; la persona escribe su contraseña al abrir la app.

```
PC de cada persona (la app)                     Servidor (este repo: el backend)
┌───────────────────────────────┐    HTTPS     ┌──────────────────────────────────┐
│ Pantallas, IA con su plan,    │ ───────────▶ │ Caddy (HTTPS automático)         │
│ vaults, agentes y memoria     │  usuario +   │  └─ backend (MARKETING_IA_MODO=  │
│                               │  contraseña  │       servidor) + PostgreSQL     │
│ Hace la IA de sus trabajos    │ ◀─────────── │  └─ respaldo diario              │
└───────────────────────────────┘   trabajos   └──────────────────────────────────┘
```

## Montaje asistido por IA
Abre Claude Code, Codex o Antigravity en el servidor y pídele:

> Clona https://github.com/anndreloopez012/marketing-digital-ia-servidor, lee su INSTALAR-CON-IA.md e instala y
> configura todo.

La IA sigue [INSTALAR-CON-IA.md](INSTALAR-CON-IA.md): revisa Docker, te pregunta el dominio, el correo del
administrador y si ya tienen PostgreSQL, y deja todo encendido con HTTPS.

## A mano
```bash
python3 montar.py diagnostico
python3 montar.py configurar --dominio marketing.tuempresa.com --correo admin@tuempresa.com [--base 'postgresql://…']
python3 montar.py traer && python3 montar.py arrancar && python3 montar.py verificar
python3 montar.py admin        # cómo ver la clave del primer administrador
```

| Archivo | Qué es |
|---|---|
| `montar.py` | Los pasos (solo biblioteca estándar) |
| `docker-compose.yml` | `app`, `caddy`, y con base propia `db` (PostgreSQL 16) y `respaldo` (pg_dump diario) |
| `Dockerfile` | La app de `./app` con PostgreSQL y FFmpeg |
| `Caddyfile` | HTTPS y proxy (sin búfer para el canal en vivo y los agentes) |
| `.env` | Lo escribe `montar.py configurar` (permisos 600, nunca se sube) |

Pruebas: `python3 -m unittest discover -s tests`.
