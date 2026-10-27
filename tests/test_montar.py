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

    def test_env_y_app_nunca_se_suben(self):
        ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").split()
        for nombre in (".env", "app/", "respaldos/"):
            self.assertIn(nombre, ignorados)


if __name__ == "__main__":
    unittest.main()
