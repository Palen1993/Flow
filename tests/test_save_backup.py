"""
Unit tests for Save Game Backup Service, Auto-Detection, Compression, Retention and Dialog.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json
import zipfile
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.save_backup_service import (
    format_bytes_size,
    _generate_name_variants,
    _get_dir_summary,
    detect_game_save_candidates,
    get_effective_save_directory,
    create_save_backup,
    list_game_backups,
    restore_save_backup,
    delete_save_backup,
    _prune_old_backups
)


class TestSaveBackupService(unittest.TestCase):

    def test_01_format_bytes_size(self):
        self.assertEqual(format_bytes_size(500), "500 B")
        self.assertEqual(format_bytes_size(2048), "2.0 KB")
        self.assertEqual(format_bytes_size(1024 * 1024 * 3), "3.0 MB")
        self.assertEqual(format_bytes_size(1024 * 1024 * 1024 * 2), "2.00 GB")

    def test_02_name_variants(self):
        variants = _generate_name_variants("Hollow Knight")
        self.assertIn("Hollow Knight", variants)
        self.assertIn("HollowKnight", variants)
        self.assertIn("Hollow_Knight", variants)

    def test_03_detect_save_candidates_configured_and_local(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Crear carpeta simulada de juego y carpeta de saves dentro
            game_dir = os.path.join(tmpdir, "HollowKnight")
            os.makedirs(game_dir, exist_ok=True)
            exe_path = os.path.join(game_dir, "hollow_knight.exe")
            with open(exe_path, "w") as f:
                f.write("mock_exe")

            saves_dir = os.path.join(game_dir, "saves")
            os.makedirs(saves_dir, exist_ok=True)
            with open(os.path.join(saves_dir, "user1.dat"), "w") as f:
                f.write("save_data_12345")

            game = {
                "name": "Hollow Knight",
                "path": exe_path
            }

            candidates = detect_game_save_candidates(game)
            self.assertTrue(len(candidates) > 0)
            best_dir = get_effective_save_directory(game)
            self.assertIsNotNone(best_dir)
            self.assertTrue(os.path.isdir(best_dir))

            # 2. Con ruta configurada explícita
            custom_dir = os.path.join(tmpdir, "MyCustomSaves")
            os.makedirs(custom_dir, exist_ok=True)
            with open(os.path.join(custom_dir, "slot1.sav"), "w") as f:
                f.write("slot1")

            game["save_path"] = custom_dir
            candidates2 = detect_game_save_candidates(game)
            self.assertEqual(candidates2[0]["path"], custom_dir)
            self.assertTrue(candidates2[0]["is_configured"])
            self.assertEqual(get_effective_save_directory(game), custom_dir)

    def test_04_create_save_backup_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saves_dir = os.path.join(tmpdir, "saves")
            os.makedirs(saves_dir, exist_ok=True)
            with open(os.path.join(saves_dir, "game.sav"), "w") as f:
                f.write("1234567890" * 100)
            sub_dir = os.path.join(saves_dir, "slots")
            os.makedirs(sub_dir, exist_ok=True)
            with open(os.path.join(sub_dir, "slot1.dat"), "w") as f:
                f.write("subslot_data")

            backups_dir = os.path.join(tmpdir, "backups")
            with patch("core.save_backup_service.BACKUPS_DIR", backups_dir):
                game = {
                    "name": "Celeste",
                    "path": os.path.join(tmpdir, "Celeste.exe"),
                    "save_path": saves_dir
                }

                res = create_save_backup(game, save_path=saves_dir, comment="Test backup", max_backups=5)
                self.assertTrue(res["success"])
                self.assertTrue(os.path.isfile(res["zip_path"]))
                self.assertEqual(res["files_count"], 2)

                # Validar contenido interno del zip
                with zipfile.ZipFile(res["zip_path"], "r") as zf:
                    names = zf.namelist()
                    self.assertIn("game.sav", names)
                    self.assertIn("slots/slot1.dat", names)
                    self.assertIn("manifest.json", names)

                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                    self.assertEqual(manifest["game_name"], "Celeste")
                    self.assertEqual(manifest["total_files"], 2)

                # Comprobar list_game_backups
                b_list = list_game_backups(game)
                self.assertEqual(len(b_list), 1)
                self.assertEqual(b_list[0]["name"], res["zip_name"])
                self.assertEqual(b_list[0]["total_files"], 2)

    def test_05_prune_old_backups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(7):
                zf_name = os.path.join(tmpdir, f"backup_{i}.zip")
                with zipfile.ZipFile(zf_name, "w") as zf:
                    zf.writestr("test.txt", f"data {i}")
                time.sleep(0.01)

            self.assertEqual(len(os.listdir(tmpdir)), 7)
            _prune_old_backups(tmpdir, max_backups=3)
            remaining = [f for f in os.listdir(tmpdir) if f.endswith(".zip")]
            self.assertEqual(len(remaining), 3)

    def test_06_restore_save_backup_with_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saves_dir = os.path.join(tmpdir, "current_saves")
            os.makedirs(saves_dir, exist_ok=True)
            with open(os.path.join(saves_dir, "save.dat"), "w") as f:
                f.write("current_save_version_1")

            backups_dir = os.path.join(tmpdir, "backups")
            with patch("core.save_backup_service.BACKUPS_DIR", backups_dir):
                game = {
                    "name": "Elden Ring",
                    "save_path": saves_dir
                }

                # Crear backup de la versión 1
                b1 = create_save_backup(game, save_path=saves_dir, comment="Version 1")
                self.assertTrue(b1["success"])

                # Modificar el archivo actual a la versión 2
                with open(os.path.join(saves_dir, "save.dat"), "w") as f:
                    f.write("corrupted_or_newer_version_2")

                # Restaurar versión 1
                res = restore_save_backup(game, b1["zip_path"], target_dir=saves_dir, create_safety_backup=True)
                self.assertTrue(res["success"])

                # Comprobar que el archivo se restauró al contenido de la versión 1
                with open(os.path.join(saves_dir, "save.dat"), "r") as f:
                    content = f.read()
                self.assertEqual(content, "current_save_version_1")

                # Comprobar que se generó un backup preventivo
                self.assertIsNotNone(res.get("safety_backup"))

                # Eliminar backup
                del_ok = delete_save_backup(b1["zip_path"])
                self.assertTrue(del_ok)
                self.assertFalse(os.path.isfile(b1["zip_path"]))

    def test_07_dialog_gamepad_navigation(self):
        from ui.dialogs.save_backup_dialog import SaveBackupDialog

        dlg = SaveBackupDialog.__new__(SaveBackupDialog)
        dlg.backups_list = [
            {"name": "b1.zip", "path": "/tmp/b1.zip"},
            {"name": "b2.zip", "path": "/tmp/b2.zip"}
        ]
        dlg.selected_backup_idx = 0
        dlg._highlight_selected_card = MagicMock()
        dlg._create_backup_action = MagicMock()
        dlg._restore_backup_prompt = MagicMock()
        dlg._delete_backup_prompt = MagicMock()
        dlg._change_save_location = MagicMock()
        dlg.close = MagicMock()

        # 1. Navegación cruceta
        dlg.handle_gamepad_input({"down": True}, {})
        self.assertEqual(dlg.selected_backup_idx, 1)

        dlg.handle_gamepad_input({"up": True}, {})
        self.assertEqual(dlg.selected_backup_idx, 0)

        # 2. Botón A: Crear copia
        dlg.handle_gamepad_input({"a": True}, {})
        dlg._create_backup_action.assert_called_once()

        # 3. Botón Start: Restaurar seleccionada
        dlg.handle_gamepad_input({"start": True}, {})
        dlg._restore_backup_prompt.assert_called_with("/tmp/b1.zip", "b1.zip")

        # 4. Botón Y: Eliminar seleccionada
        dlg.handle_gamepad_input({"y": True}, {})
        dlg._delete_backup_prompt.assert_called_with("/tmp/b1.zip", "b1.zip")

        # 5. Botón X: Cambiar carpeta
        dlg.handle_gamepad_input({"x": True}, {})
        dlg._change_save_location.assert_called_once()

        # 6. Botón B: Cerrar
        dlg.handle_gamepad_input({"b": True}, {})
        dlg.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
