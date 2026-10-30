import sys
import os
import unittest
import tempfile
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.config import (
    get_storage_dir, is_portable_mode, STORAGE_DIR,
    CONFIG_FILE, COVERS_DIR, WALLPAPERS_DIR, GAMEPAD_CONFIG_FILE,
    _determine_storage_dir
)

class TestPortabilityAndStorage(unittest.TestCase):
    def test_01_current_storage_is_valid_and_writable(self):
        """Verifica que el almacenamiento activo actual es un directorio válido y escribible."""
        storage = get_storage_dir()
        self.assertTrue(os.path.isdir(storage))
        self.assertIsInstance(is_portable_mode(), bool)
        
        # Debe poder escribir un archivo temporal sin PermissionError
        test_file = os.path.join(storage, f".perm_unit_test_{os.getpid()}.tmp")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("gameflow_ok")
            self.assertTrue(os.path.isfile(test_file))
        finally:
            if os.path.isfile(test_file):
                os.remove(test_file)

    def test_02_directories_exist(self):
        """Verifica que las carpetas de recursos requeridas existen."""
        self.assertTrue(os.path.isdir(COVERS_DIR))
        self.assertTrue(os.path.isdir(WALLPAPERS_DIR))

    def test_03_fallback_to_appdata_on_readonly_base_dir(self):
        """Simula un BASE_DIR protegido (PermissionError) y valida el desvío a %APPDATA%\\GameFlow."""
        with tempfile.TemporaryDirectory() as fake_appdata:
            with patch("os.environ.get", return_value=fake_appdata):
                # Simular open() fallando con PermissionError en la prueba de permisos
                real_open = open
                def mock_open(path, *args, **kwargs):
                    if ".perm_test_" in str(path):
                        raise PermissionError("Access is denied (Mock UAC)")
                    return real_open(path, *args, **kwargs)

                with patch("builtins.open", side_effect=mock_open):
                    resolved_dir = _determine_storage_dir()
                    expected_target = os.path.join(fake_appdata, "GameFlow")
                    self.assertEqual(os.path.normpath(resolved_dir), os.path.normpath(expected_target))
                    self.assertTrue(os.path.isdir(resolved_dir))

    def test_04_portable_marker_forces_local_storage(self):
        """Verifica que la presencia de .portable fuerza el modo local."""
        with patch("os.path.isfile", side_effect=lambda p: True if p.endswith(".portable") else os.path.isfile(p)):
            resolved_dir = _determine_storage_dir()
            self.assertEqual(os.path.normpath(resolved_dir), os.path.normpath(BASE_DIR))

if __name__ == "__main__":
    unittest.main()
