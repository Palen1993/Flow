"""
Tests unitarios para el servicio de Sincronización de Partidas en la Nube (Cloud Save Sync)
y sus diálogos/integraciones asociadas.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import shutil
import zipfile
import base64

# Asegurar path al proyecto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.cloud_sync_service import (
    load_cloud_config,
    save_cloud_config,
    is_cloud_sync_enabled,
    detect_local_cloud_providers,
    test_cloud_connection,
    upload_backup_to_cloud,
    list_cloud_backups,
    download_cloud_backup,
    sync_game_backups,
    sync_all_games,
    maybe_auto_sync_backup,
    WebDAVClient,
    PROVIDER_ONEDRIVE,
    PROVIDER_GDRIVE,
    PROVIDER_LOCAL_FOLDER,
    PROVIDER_WEBDAV
)


class TestCloudSyncService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cloud_folder = os.path.join(self.temp_dir, "CloudStorage")
        os.makedirs(self.cloud_folder, exist_ok=True)
        self._cfg_patcher = patch(
            "core.cloud_sync_service.CLOUD_SYNC_CONFIG_FILE",
            os.path.join(self.temp_dir, "cloud_sync.json"),
        )
        self._cfg_patcher.start()

        self.game = {
            "name": "Hollow Knight",
            "path": "C:\\Games\\HollowKnight\\hollow_knight.exe"
        }

        # Crear un archivo zip de prueba para el backup
        self.sample_zip = os.path.join(self.temp_dir, "Hollow_Knight_Save_20261110_120000.zip")
        with zipfile.ZipFile(self.sample_zip, "w") as zf:
            zf.writestr("user1.dat", b"save_data_sample_content")
            zf.writestr("manifest.json", b'{"game_name": "Hollow Knight"}')

        self.test_cfg = {
            "enabled": True,
            "provider": PROVIDER_LOCAL_FOLDER,
            "local_cloud_path": self.cloud_folder,
            "subfolder_name": "GameFlow_Saves",
            "webdav_url": "",
            "webdav_user": "",
            "webdav_password": "",
            "auto_sync_on_backup": True,
            "last_sync_time": "",
            "last_sync_status": "none",
            "last_sync_error": "",
            "synced_files": {}
        }

    def tearDown(self):
        try:
            self._cfg_patcher.stop()
        except Exception:
            pass
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_provider_detection_onedrive(self):
        """Verifica la detección automática de OneDrive si la variable de entorno existe."""
        fake_od = os.path.join(self.temp_dir, "MockOneDrive")
        os.makedirs(fake_od, exist_ok=True)

        with patch.dict(os.environ, {"OneDrive": fake_od}):
            providers = detect_local_cloud_providers()
            od = next((p for p in providers if p["provider"] == PROVIDER_ONEDRIVE), None)
            self.assertIsNotNone(od)
            self.assertEqual(od["path"], os.path.normpath(fake_od))

    def test_config_load_and_save(self):
        """Verifica la persistencia atómica de la configuración de Cloud Sync."""
        with patch("core.cloud_sync_service.CLOUD_SYNC_CONFIG_FILE", os.path.join(self.temp_dir, "cloud_sync.json")):
            res = save_cloud_config(self.test_cfg)
            self.assertTrue(res)

            loaded = load_cloud_config()
            self.assertTrue(loaded["enabled"])
            self.assertEqual(loaded["local_cloud_path"], self.cloud_folder)

    def test_is_cloud_sync_enabled(self):
        """Comprueba el estado activo/inactivo según la configuración."""
        with patch("core.cloud_sync_service.load_cloud_config", return_value=self.test_cfg):
            self.assertTrue(is_cloud_sync_enabled())

        disabled_cfg = dict(self.test_cfg, enabled=False)
        with patch("core.cloud_sync_service.load_cloud_config", return_value=disabled_cfg):
            self.assertFalse(is_cloud_sync_enabled())

    def test_test_connection_local_folder(self):
        """Prueba la validación y permisos de escritura en carpeta en la nube."""
        success, msg = test_cloud_connection(self.test_cfg)
        self.assertTrue(success)
        self.assertIn("Acceso correcto", msg)

        # Carpeta inexistente inválida
        bad_cfg = dict(self.test_cfg, local_cloud_path=os.path.join(self.temp_dir, "non_existent", "sub"))
        success_bad, _ = test_cloud_connection(bad_cfg)
        # Debe crearla o retornar True
        self.assertTrue(success_bad)

    def test_upload_and_list_backup_local_folder(self):
        """Prueba la subida de un backup a la nube y su posterior listado."""
        with patch("core.cloud_sync_service.load_cloud_config", return_value=self.test_cfg):
            with patch("core.cloud_sync_service.save_cloud_config"):
                res = upload_backup_to_cloud(self.game, self.sample_zip, self.test_cfg)
                self.assertTrue(res["success"])
                self.assertIn("Hollow_Knight", res["remote_ref"])

                # Verificar que el archivo existe físicamente en el destino de la nube
                self.assertTrue(os.path.isfile(res["remote_ref"]))

                # Listar backups en la nube
                cloud_items = list_cloud_backups(self.game, self.test_cfg)
                self.assertEqual(len(cloud_items), 1)
                self.assertEqual(cloud_items[0]["name"], os.path.basename(self.sample_zip))
                self.assertGreater(cloud_items[0]["size_bytes"], 0)

    def test_download_cloud_backup(self):
        """Prueba la descarga de un archivo de la nube a la carpeta local de backups."""
        # 1. Subir
        upload_backup_to_cloud(self.game, self.sample_zip, self.test_cfg)
        cloud_items = list_cloud_backups(self.game, self.test_cfg)
        self.assertEqual(len(cloud_items), 1)

        # 2. Descargar a una carpeta destino simulada
        mock_local_backup_dir = os.path.join(self.temp_dir, "LocalGameBackups")
        with patch("core.cloud_sync_service.get_game_backup_directory", return_value=mock_local_backup_dir):
            success, dest = download_cloud_backup(self.game, cloud_items[0], self.test_cfg)
            self.assertTrue(success)
            self.assertTrue(os.path.isfile(dest))
            self.assertEqual(os.path.basename(dest), os.path.basename(self.sample_zip))

    def test_sync_game_backups(self):
        """Prueba la sincronización de todos los backups locales pendientes de un juego."""
        mock_backups = [
            {"name": os.path.basename(self.sample_zip), "path": self.sample_zip}
        ]
        with patch("core.save_backup_service.list_game_backups", return_value=mock_backups):
            with patch("core.cloud_sync_service.save_cloud_config"):
                res = sync_game_backups(self.game, self.test_cfg)
                self.assertTrue(res["success"])
                self.assertEqual(res["uploaded"], 1)

    def test_sync_all_games(self):
        """Prueba la sincronización masiva de la biblioteca."""
        games = [self.game, {"name": "Celeste", "path": "C:\\Games\\Celeste\\celeste.exe"}]
        with patch("core.cloud_sync_service.load_cloud_config", return_value=self.test_cfg):
            with patch("core.cloud_sync_service.sync_game_backups", return_value={"success": True, "uploaded": 1, "errors": []}):
                progress_calls = []
                res = sync_all_games(games, progress_cb=lambda idx, tot, name: progress_calls.append(name))
                self.assertTrue(res["success"])
                self.assertEqual(res["total_uploaded"], 2)
                self.assertEqual(len(progress_calls), 2)


class TestWebDAVClient(unittest.TestCase):

    def test_webdav_auth_header_and_url(self):
        """Verifica que el cliente WebDAV construya headers Basic Auth y URLs válidas."""
        client = WebDAVClient("https://nextcloud.example.com/remote.php/dav/files/user", "testuser", "secretpass")
        headers = client._get_auth_header()
        self.assertIn("Authorization", headers)
        self.assertTrue(headers["Authorization"].startswith("Basic "))

        # Verificar decodificación base64
        b64 = headers["Authorization"].split(" ")[1]
        decoded = base64.b64decode(b64).decode("utf-8")
        self.assertEqual(decoded, "testuser:secretpass")

        url = client._build_url("GameFlow_Saves/Hollow Knight/save.zip")
        self.assertIn("https://nextcloud.example.com/remote.php/dav/files/user/GameFlow_Saves/Hollow%20Knight/save.zip", url)

    def test_webdav_propfind_xml_parsing(self):
        """Verifica el parseo de respuestas XML PROPFIND de Nextcloud/ownCloud."""
        mock_xml = b"""<?xml version="1.0"?>
        <d:multistatus xmlns:d="DAV:">
            <d:response>
                <d:href>/remote.php/dav/files/user/GameFlow_Saves/Hollow%20Knight/</d:href>
                <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
            </d:response>
            <d:response>
                <d:href>/remote.php/dav/files/user/GameFlow_Saves/Hollow%20Knight/HK_Save_20261110.zip</d:href>
                <d:propstat>
                    <d:prop>
                        <d:getcontentlength>54321</d:getcontentlength>
                        <d:getlastmodified>Tue, 10 Nov 2026 22:00:00 GMT</d:getlastmodified>
                    </d:prop>
                </d:propstat>
            </d:response>
        </d:multistatus>"""

        client = WebDAVClient("https://nextcloud.example.com")
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_xml
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            files = client.list_files("GameFlow_Saves/Hollow Knight")
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["name"], "HK_Save_20261110.zip")
            self.assertEqual(files[0]["size_bytes"], 54321)


class TestCloudSyncDialog(unittest.TestCase):

    def test_dialog_gamepad_navigation(self):
        """Prueba la navegación con mando en CloudSyncDialog."""
        from ui.dialogs.cloud_sync_dialog import CloudSyncDialog

        dlg = CloudSyncDialog.__new__(CloudSyncDialog)
        dlg.selected_provider = PROVIDER_ONEDRIVE
        dlg.close = MagicMock()
        dlg._on_sync_now = MagicMock()
        dlg._on_browse_folder = MagicMock()
        dlg._on_test_connection = MagicMock()
        dlg._on_select_provider = MagicMock()

        # D-pad derecha cicla proveedor
        dlg.handle_gamepad_input({"right": True}, {"right": False})
        dlg._on_select_provider.assert_called_once_with(PROVIDER_GDRIVE)

        # Botón Start sincroniza ahora
        dlg.handle_gamepad_input({"start": True}, {"start": False})
        dlg._on_sync_now.assert_called_once()

        # Botón A prueba conexión
        dlg.handle_gamepad_input({"a": True}, {"a": False})
        dlg._on_test_connection.assert_called_once()

        # Botón B cierra diálogo
        dlg.handle_gamepad_input({"b": True}, {"b": False})
        dlg.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
