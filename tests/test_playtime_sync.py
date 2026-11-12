import os
import sys
import time
import json
import tempfile
import unittest

# Añadir raíz
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import core.config as config_mod

class TestPlaytimeSynchronization(unittest.TestCase):
    def setUp(self):
        self.orig_config_file = config_mod.CONFIG_FILE
        self.test_dir = tempfile.mkdtemp()
        self.test_config_file = os.path.join(self.test_dir, "test_games.json")
        config_mod.CONFIG_FILE = self.test_config_file

    def tearDown(self):
        config_mod.CONFIG_FILE = self.orig_config_file
        try:
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    @unittest.skipUnless(os.name == "nt", "Win32 kernel32 mutex solo disponible en Windows")
    def test_01_config_lock_context(self):
        """Verifica que config_lock adquiere y libera el mutex del kernel sin excepciones."""
        with config_mod.config_lock(timeout_ms=1000) as acquired:
            self.assertTrue(acquired)

    def test_02_record_game_session_by_path(self):
        """Verifica el registro atómico de sesión usando la ruta canónica del juego."""
        initial_games = [
            {
                "name": "Game Alpha",
                "path": "C:\\Games\\Alpha\\alpha.exe",
                "playtime_minutes": 10,
                "last_played": "2026-10-01 10:00"
            },
            {
                "name": "Game Beta",
                "path": "C:\\Games\\Beta\\beta.exe",
                "playtime_minutes": 60,
                "last_played": "2026-10-01 10:00"
            }
        ]
        config_mod.save_games_data(initial_games, merge_existing_playtime=False)

        # Simular 30 minutos jugados (1800 seg) en Game Alpha
        res = config_mod.record_game_session("C:\\Games\\Alpha\\alpha.exe", 1800.0)
        self.assertTrue(res)

        loaded = config_mod.load_games_data()
        alpha = next(g for g in loaded if g["name"] == "Game Alpha")
        self.assertEqual(alpha["playtime_minutes"], 40)
        self.assertTrue(alpha["last_played"].startswith("2026-"))

    @unittest.skipUnless(os.name == "nt", "Resolución de rutas con barra invertida Windows requiere Windows")
    def test_03_record_game_session_fallback_by_exe(self):
        """Verifica el registro de sesión por nombre de ejecutable si la ruta difiere ligeramente."""
        initial_games = [
            {
                "name": "Game Delta",
                "path": "D:\\SteamLibrary\\delta.exe",
                "playtime_minutes": 5,
                "last_played": "2026-10-01 10:00"
            }
        ]
        config_mod.save_games_data(initial_games, merge_existing_playtime=False)

        # Simular 15 minutos jugados por exe_base
        res = config_mod.record_game_session("", 900.0, exe_base="delta.exe")
        self.assertTrue(res)

        loaded = config_mod.load_games_data()
        delta = next(g for g in loaded if g["name"] == "Game Delta")
        self.assertEqual(delta["playtime_minutes"], 20)

    def test_04_save_games_preserves_background_playtime(self):
        """
        ESCENARIO CRÍTICO DE CARRERA:
        La app en memoria tiene 10 mins de Alpha.
        El centinela en segundo plano graba +45 mins (ahora 55 mins en disco).
        La app guarda sus datos en memoria (que aún tenían 10 mins).
        save_games_data DEBE fusionar y preservar los 55 mins en lugar de sobreescribirlos con 10 mins.
        """
        initial_games = [
            {
                "name": "Game Alpha",
                "path": "C:\\Games\\Alpha\\alpha.exe",
                "playtime_minutes": 10,
                "last_played": "2026-10-01 10:00"
            }
        ]
        config_mod.save_games_data(initial_games, merge_existing_playtime=False)

        # 1. La app tiene una copia en memoria:
        in_memory_app_copy = [dict(g) for g in initial_games]

        # 2. El centinela actualiza en segundo plano directamente en disco:
        config_mod.record_game_session("C:\\Games\\Alpha\\alpha.exe", 45 * 60.0)

        # Comprobar que en disco ahora hay 55 mins:
        disk_data = config_mod.load_games_data()
        self.assertEqual(disk_data[0]["playtime_minutes"], 55)

        # 3. La app llama a save_games_data con su copia vieja (10 mins) y una modificación del usuario (ej: monitor cambiado)
        in_memory_app_copy[0]["monitor"] = 2
        config_mod.save_games_data(in_memory_app_copy, merge_existing_playtime=True)

        # 4. Verificar que en disco se preservaron los 55 mins y se guardó el nuevo monitor:
        final_disk_data = config_mod.load_games_data()
        self.assertEqual(final_disk_data[0]["playtime_minutes"], 55)
        self.assertEqual(final_disk_data[0]["monitor"], 2)

    def test_05_file_mtime_reactivity(self):
        """Verifica que get_games_file_mtime refleja modificaciones."""
        initial_games = [{"name": "Test", "path": "test.exe"}]
        config_mod.save_games_data(initial_games, merge_existing_playtime=False)
        mtime1 = config_mod.get_games_file_mtime()
        self.assertGreater(mtime1, 0.0)

        time.sleep(0.05)
        config_mod.save_games_data(initial_games, merge_existing_playtime=False)
        mtime2 = config_mod.get_games_file_mtime()
        self.assertGreaterEqual(mtime2, mtime1)

if __name__ == "__main__":
    unittest.main()
