"""montar.py como lo conduce una IA: configurar escribe .env (solo para el dueño, con secretos nuevos que no se pisan al
repetir), valida dominio, correo y base; diagnóstico dice qué falta sin tocar nada; los comandos de Docker se arman
con el perfil correcto. Sin Docker ni red: los comandos se capturan, no se corren."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import montar  # noqa: E402


class ConfigurarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.env = Path(self.tmp.name) / ".env"

    def leer(self):
        return montar.leer_env(self.env)

    def test_escribe_env_solo_para_el_dueno_con_base_propia(self):
        montar.configurar_env(self.env, dominio="marketing.empresa.com", correo="admin@empresa.com")
        e = self.leer()
        self.assertEqual((e["DOMINIO"], e["CORREO_ADMIN"], e["BASE"]), ("marketing.empresa.com", "admin@empresa.com", "propia"))
        self.assertGreaterEqual(len(e["POSTGRES_PASSWORD"]), 32)
        self.assertEqual(e["DATABASE_URL"], f"postgresql://marketing:{e['POSTGRES_PASSWORD']}@db:5432/marketing_ia")
        self.assertEqual(e["APP_REPO"], montar.APP_REPO)
        self.assertEqual(stat.S_IMODE(os.stat(self.env).st_mode), 0o600)

    def test_repetir_no_cambia_la_clave_de_la_base(self):
        montar.configurar_env(self.env, dominio="a.empresa.com", correo="admin@empresa.com")
        clave = self.leer()["POSTGRES_PASSWORD"]
        montar.configurar_env(self.env, dominio="b.empresa.com", correo="otro@empresa.com", version="v2")
        e = self.leer()
        self.assertEqual((e["POSTGRES_PASSWORD"], e["DOMINIO"], e["APP_VERSION"]), (clave, "b.empresa.com", "v2"))

    def test_base_externa(self):
        montar.configurar_env(self.env, dominio="m.empresa.com", correo="a@empresa.com",
                              base="postgresql://usuario:clave@base.empresa.com:5432/marketing")
        e = self.leer()
        self.assertEqual((e["BASE"], e["DATABASE_URL"]), ("externa", "postgresql://usuario:clave@base.empresa.com:5432/marketing"))

    def test_rechaza_lo_invalido_sin_escribir(self):
        for kwargs in ({"dominio": "https://m.empresa.com", "correo": "a@empresa.com"},
                       {"dominio": "m empresa", "correo": "a@empresa.com"},
                       {"dominio": "m.empresa.com", "correo": "no-es-correo"},
                       {"dominio": "m.empresa.com", "correo": "a@empresa.com", "base": "mysql://x"}):
            with self.assertRaises(ValueError, msg=kwargs):
                montar.configurar_env(self.env, **kwargs)
        self.assertFalse(self.env.exists())

    def test_localhost_para_probar(self):
        montar.configurar_env(self.env, dominio="localhost", correo="a@empresa.com", puertos=(8080, 8443))
        e = self.leer()
        self.assertEqual((e["PUERTO_HTTP"], e["PUERTO_HTTPS"], e["PUERTO_HTTPS_PUBLICO"]), ("8080", "8443", ":8443"))


class ComandosTests(unittest.TestCase):
    def test_perfil_segun_la_base(self):
        self.assertEqual(montar.compose_base({"BASE": "propia"}), ["docker", "compose", "--profile", "base-propia"])
        self.assertEqual(montar.compose_base({"BASE": "externa"}), ["docker", "compose"])

    def test_la_url_de_salud(self):
        self.assertEqual(montar.url_salud({"DOMINIO": "m.empresa.com"}), "https://m.empresa.com/api/health")
        self.assertEqual(montar.url_salud({"DOMINIO": "localhost", "PUERTO_HTTPS_PUBLICO": ":8443"}), "https://localhost:8443/api/health")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.entorno = {**os.environ, "MONTAR_RAIZ": self.tmp.name, "PATH": "/usr/bin:/bin"}

    def correr(self, *args):
        r = subprocess.run([sys.executable, str(RAIZ / "montar.py"), *args], capture_output=True, text=True, env=self.entorno, timeout=60)
        return r.returncode, r.stdout, r.stderr

    def test_diagnostico_en_json_dice_lo_pendiente(self):
        code, out, err = self.correr("diagnostico", "--json")
        self.assertEqual(code, 0, err)
        d = json.loads(out)
        for clave in ("docker", "compose", "git", "configurado", "app", "pendiente"):
            self.assertIn(clave, d)
        self.assertFalse(d["configurado"])
        self.assertTrue(any("configurar" in p for p in d["pendiente"]))

    def test_configurar_por_la_cli_y_nunca_muestra_la_clave(self):
        code, out, err = self.correr("configurar", "--dominio", "m.empresa.com", "--correo", "a@empresa.com", "--json")
        self.assertEqual(code, 0, err)
        clave = montar.leer_env(Path(self.tmp.name) / ".env")["POSTGRES_PASSWORD"]
        self.assertNotIn(clave, out + err)
        self.assertEqual(json.loads(out)["dominio"], "m.empresa.com")
        code, out, err = self.correr("configurar", "--dominio", "mal dominio", "--correo", "a@empresa.com", "--json")
        self.assertEqual(code, 1)
        self.assertIn("dominio", json.loads(out)["error"])

    def test_arrancar_sin_configurar_lo_dice(self):
        code, out, err = self.correr("arrancar", "--json")
        self.assertEqual(code, 1)
        self.assertIn("configurar", json.loads(out)["error"])


class ArchivosTests(unittest.TestCase):
    def test_compose_trae_lo_que_la_app_necesita_en_el_servidor(self):
        texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
        for linea in ("MARKETING_IA_MODO: servidor", "MARKETING_IA_DOCUMENTOS: base", 'AUTH_REQUIRED: "1"', "HOST: 0.0.0.0",
                      "image: postgres:16-alpine", "image: caddy:2-alpine", "pg_dump"):
            self.assertIn(linea, texto)

    def test_compose_declara_la_zona_y_el_vault_del_servidor(self):
        texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("MARKETING_IA_ZONA: ${ZONA:-America/Guatemala}", texto)   # sin ella las fechas viejas no se migran
        self.assertIn("CAMPUS_VAULT: /datos/vault", texto)   # sin ella la memoria iría a la carpeta personal del contenedor

    def test_la_imagen_trae_pg_dump_para_los_respaldos_de_la_pantalla(self):
        self.assertIn("postgresql-client", (RAIZ / "Dockerfile").read_text(encoding="utf-8"))

    def test_env_y_app_nunca_se_suben(self):
        ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").split()
        for nombre in (".env", "app/", "respaldos/"):
            self.assertIn(nombre, ignorados)


class ActualizarTests(unittest.TestCase):
    """Actualizar a prueba de errores: respaldo antes (sin él no se sigue), se anota la versión anterior, la comprobación
    final mira la versión que publica /api/health y `volver` regresa a la anterior. Sin Docker ni red."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        raiz = Path(self.tmp.name)
        for nombre, valor in (("RAIZ", raiz), ("ENV", raiz / ".env"), ("APP", raiz / "app")):
            parche = mock.patch.object(montar, nombre, valor); parche.start(); self.addCleanup(parche.stop)
        montar.configurar_env(raiz / ".env", dominio="m.empresa.com", correo="a@empresa.com", version="v2026.8")
        (raiz / "app").mkdir()
        (raiz / "app" / "app.py").write_text("")
        (raiz / "app" / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2026.10"\n')
        self.cmds, self.falla = [], set()

        def correr(cmd, **kw):
            self.cmds.append(cmd)
            if kw.get("stdout") is not None and "pg_dump" in cmd:
                kw["stdout"].write("-- respaldo\n")
            codigo = 1 if any(p in " ".join(cmd) for p in self.falla) else 0
            return subprocess.CompletedProcess(cmd, codigo, stdout="abc1234\n", stderr="")
        parche = mock.patch.object(montar, "_correr", side_effect=correr); parche.start(); self.addCleanup(parche.stop)
        self.salud = {"ok": True, "version": "2026.10", "api": 2}
        parche = mock.patch.object(montar, "_leer_salud", side_effect=lambda env, esperar: self.salud); parche.start(); self.addCleanup(parche.stop)
        self.args = mock.Mock(json=True, version="v2026.10", esperar="1", sin_respaldo=False, respaldo=None, confirmar=False)

    def test_respalda_antes_y_anota_la_version_anterior(self):
        self.assertEqual(montar.actualizar(self.args), 0)
        juntos = [" ".join(c) for c in self.cmds]
        self.assertIn("pg_dump", juntos[0], "lo primero es el respaldo de la base")
        self.assertTrue(any("up -d --build" in c for c in juntos))
        env = montar.leer_env(montar.ENV)
        self.assertEqual((env["APP_VERSION"], env["APP_VERSION_ANTERIOR"]), ("v2026.10", "v2026.8"))
        self.assertTrue(list((montar.RAIZ / "respaldos").glob("antes-de-v2026.10-*.sql")))

    def test_sin_respaldo_no_actualiza(self):
        self.falla.add("pg_dump")
        self.assertEqual(montar.actualizar(self.args), 1)
        self.assertFalse(any("up" in c for c in self.cmds), "sin respaldo no se toca nada")
        self.assertEqual(montar.leer_env(montar.ENV)["APP_VERSION"], "v2026.8")

    def test_si_la_salud_no_dice_la_version_nueva_lo_avisa_con_la_vuelta_atras(self):
        self.salud = {"ok": True}
        with mock.patch("builtins.print") as impreso:
            self.assertEqual(montar.actualizar(self.args), 1)
        texto = " ".join(str(a) for llamada in impreso.call_args_list for a in llamada.args)
        self.assertIn("volver", texto)

    def test_volver_regresa_a_la_version_anterior(self):
        montar.actualizar(self.args)
        self.cmds.clear()
        self.salud = {"ok": True, "version": "2026.10", "api": 2}
        self.assertEqual(montar.volver(mock.Mock(json=True, version=None, respaldo=None, confirmar=False, esperar="1")), 0)
        env = montar.leer_env(montar.ENV)
        self.assertEqual(env["APP_VERSION"], "v2026.8")
        self.assertTrue(any(c[0] == "git" and "v2026.8" in c for c in self.cmds), "trae la versión anterior")

    def test_volver_con_la_base_pide_confirmar(self):
        respaldo = montar.RAIZ / "r.sql"; respaldo.write_text("-- x")
        self.assertEqual(montar.volver(mock.Mock(json=True, version="v2026.8", respaldo=str(respaldo), confirmar=False, esperar="1")), 1)
        self.assertFalse(any("psql" in " ".join(c) for c in self.cmds))
        self.assertEqual(montar.volver(mock.Mock(json=True, version="v2026.8", respaldo=str(respaldo), confirmar=True, esperar="1")), 0)
        self.assertTrue(any("psql" in " ".join(c) for c in self.cmds))

    def test_la_salud_compara_la_version_de_la_app_traida(self):
        self.assertEqual(montar.version_traida(), "2026.10")
        self.assertTrue(montar.al_dia({"version": "2026.10", "api": 2}))
        self.assertFalse(montar.al_dia({"ok": True}))
        self.assertFalse(montar.al_dia({"version": "2026.9", "api": 1}))


if __name__ == "__main__":
    unittest.main()
