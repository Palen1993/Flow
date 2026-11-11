"""
Suite de Pruebas Unitarias para Modo Kiosco, Emuladores de ROMs y Descarga de Wallpapers 16:9
"""
import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Añadir raíz del proyecto al sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.kiosk_service import (
    is_kiosk_shell_active, enable_kiosk_shell, disable_kiosk_shell,
    is_autostart_active, set_autostart, launch_windows_explorer,
    get_kiosk_status, get_launcher_executable_path
)
from core.emulator_service import (
    SUPPORTED_SYSTEMS, get_all_supported_rom_extensions, detect_system_for_file,
    clean_rom_name, load_emulators_config, save_emulators_config,
    get_emulator_for_system, build_rom_launch_command, scan_folder_for_roms
)
from core.execution_service import GameExecutionService


class TestKioskService(unittest.TestCase):
    def test_kiosk_status_dict(self):
        status = get_kiosk_status()
        self.assertIn("is_windows", status)
        self.assertIn("kiosk_active", status)
        self.assertIn("autostart_active", status)
        self.assertIn("current_shell", status)
        self.assertIn("launcher_cmd", status)

    def test_launcher_path(self):
        cmd = get_launcher_executable_path()
        self.assertTrue(len(cmd) > 0)
        self.assertTrue("lanzador" in cmd.lower() or "python" in cmd.lower() or ".exe" in cmd.lower())

    @patch("core.kiosk_service.is_windows", return_value=False)
    def test_non_windows_safeguards(self, mock_is_win):
        # En sistemas no-Windows, las funciones deben fallar limpiamente sin crash
        self.assertFalse(is_kiosk_shell_active())
        self.assertFalse(is_autostart_active())
        ok, msg = enable_kiosk_shell()
        self.assertFalse(ok)
        self.assertIn("Windows", msg)
        ok2, msg2 = set_autostart(True)
        self.assertFalse(ok2)
        ok3, _ = launch_windows_explorer()
        self.assertFalse(ok3)

    @patch("core.kiosk_service.is_windows", return_value=True)
    def test_windows_registry_simulation(self, mock_is_win):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.CreateKey.return_value.__enter__.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ('"C:\\GameFlow\\GameFlow.exe"', 1)
        mock_winreg.HKEY_CURRENT_USER = 0x80000001
        mock_winreg.KEY_READ = 0x20019
        mock_winreg.KEY_SET_VALUE = 0x0002
        mock_winreg.REG_SZ = 1

        with patch("core.kiosk_service.winreg", mock_winreg):
            self.assertTrue(is_kiosk_shell_active())
            ok, msg = enable_kiosk_shell()
            self.assertTrue(ok)
            mock_winreg.SetValueEx.assert_called()

            ok_dis, _ = disable_kiosk_shell()
            self.assertTrue(ok_dis)
            mock_winreg.DeleteValue.assert_called()


class TestEmulatorService(unittest.TestCase):
    def test_supported_systems_catalog(self):
        self.assertTrue(len(SUPPORTED_SYSTEMS) >= 15)
        sys_ids = {s["id"] for s in SUPPORTED_SYSTEMS}
        self.assertIn("snes", sys_ids)
        self.assertIn("ps1", sys_ids)
        self.assertIn("ps2", sys_ids)
        self.assertIn("gamecube", sys_ids)
        self.assertIn("gba", sys_ids)
        self.assertIn("genesis", sys_ids)

    def test_all_supported_extensions(self):
        exts = get_all_supported_rom_extensions()
        self.assertIn(".sfc", exts)
        self.assertIn(".nes", exts)
        self.assertIn(".gba", exts)
        self.assertIn(".iso", exts)
        self.assertIn(".chd", exts)
        self.assertIn(".rvz", exts)
        self.assertIn(".nsp", exts)

    def test_detect_system_direct(self):
        sfc = detect_system_for_file("C:/Games/Zelda.sfc")
        self.assertIsNotNone(sfc)
        self.assertEqual(sfc["id"], "snes")

        gba = detect_system_for_file("D:/ROMs/Pokemon.gba")
        self.assertIsNotNone(gba)
        self.assertEqual(gba["id"], "gba")

        rvz = detect_system_for_file("E:/Wii/MarioGalaxy.rvz")
        self.assertIsNotNone(rvz)
        self.assertEqual(rvz["id"], "gamecube")

        chd = detect_system_for_file("C:/Retro/MetalGearSolid.chd")
        self.assertIsNotNone(chd)
        self.assertEqual(chd["id"], "ps1")

    def test_detect_system_disambiguation(self):
        # Extensiones compartidas como .iso desambiguadas por la ruta
        ps2_iso = detect_system_for_file("C:/Roms/PS2/GranTurismo4.iso")
        self.assertIsNotNone(ps2_iso)
        self.assertEqual(ps2_iso["id"], "ps2")

        gc_iso = detect_system_for_file("D:/Emulacion/GameCube/SmashMelee.iso")
        self.assertIsNotNone(gc_iso)
        self.assertEqual(gc_iso["id"], "gamecube")

        psp_iso = detect_system_for_file("E:/Retro/PSP/GodOfWar.iso")
        self.assertIsNotNone(psp_iso)
        self.assertEqual(psp_iso["id"], "psp")

    def test_clean_rom_name(self):
        self.assertEqual(clean_rom_name("Super Mario World (USA).sfc"), "Super Mario World")
        self.assertEqual(clean_rom_name("Pokemon - Emerald Version (USA, Europe) [!].gba"), "Pokemon - Emerald Version")
        self.assertEqual(clean_rom_name("Crash_Bandicoot_3_Warped_(Europe)_(En,Fr,De,Es,It).bin"), "Crash Bandicoot 3 Warped")
        self.assertEqual(clean_rom_name("The Legend of Zelda - Ocarina of Time (v1.2) (Rev B) [b1].z64"), "The Legend of Zelda - Ocarina of Time")
        self.assertEqual(clean_rom_name("Gran Turismo 4 (USA) (Track 01).chd"), "Gran Turismo 4")

    def test_config_save_load(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmp_dir, "test_emulators.json")
            test_data = {
                "retroarch_path": "C:/RetroArch/retroarch.exe",
                "systems": {
                    "snes": {
                        "emulator_path": "C:/Emus/snes9x.exe",
                        "args_template": "{rom}"
                    }
                }
            }
            ok = save_emulators_config(test_data, cfg_path)
            self.assertTrue(ok)
            loaded = load_emulators_config(cfg_path)
            self.assertEqual(loaded["retroarch_path"], test_data["retroarch_path"])
            self.assertEqual(loaded["systems"]["snes"]["emulator_path"], "C:/Emus/snes9x.exe")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_build_rom_launch_command(self):
        # Con ejecutable explícito y plantilla
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f_emu, \
             tempfile.NamedTemporaryFile(suffix=".sfc", delete=False) as f_rom:
            f_emu.write(b"mock")
            f_rom.write(b"mock")
            f_emu_path = f_emu.name
            f_rom_path = f_rom.name

        try:
            exe, args = build_rom_launch_command(
                rom_path=f_rom_path,
                emulator_path=f_emu_path,
                system_id="snes",
                custom_args="-fullscreen {rom}"
            )
            self.assertEqual(exe, f_emu_path)
            self.assertIn(f'"{os.path.abspath(f_rom_path)}"', args)
            self.assertTrue(args.startswith("-fullscreen"))
        finally:
            if os.path.isfile(f_emu_path):
                os.remove(f_emu_path)
            if os.path.isfile(f_rom_path):
                os.remove(f_rom_path)

    def test_scan_folder_for_roms(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            # Crear ROMs de prueba
            rom1 = os.path.join(tmp_dir, "Chrono Trigger (USA).sfc")
            rom2 = os.path.join(tmp_dir, "Sonic The Hedgehog (USA, Europe).md")
            fake_txt = os.path.join(tmp_dir, "readme.txt")

            with open(rom1, "w") as f: f.write("mock")
            with open(rom2, "w") as f: f.write("mock")
            with open(fake_txt, "w") as f: f.write("mock")

            results = scan_folder_for_roms(tmp_dir, recursive=False)
            self.assertEqual(len(results), 2)

            titles = {r["name"] for r in results}
            self.assertIn("Chrono Trigger", titles)
            self.assertIn("Sonic The Hedgehog", titles)

            for r in results:
                self.assertTrue(r["is_rom"])
                self.assertTrue(len(r["collections"]) > 0)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


class TestExecutionServiceIntegration(unittest.TestCase):
    @patch("core.execution_service.launch_game_thread")
    def test_execution_service_passes_rom_params(self, mock_launch_thread):
        service = GameExecutionService()
        test_game = {
            "name": "Super Mario World",
            "path": "C:/Roms/SMW.sfc",
            "monitor": 1,
            "high_priority": True,
            "launch_args": "-fullscreen",
            "is_rom": True,
            "system_id": "snes",
            "emulator_path": "C:/Emus/snes9x.exe"
        }

        ok = service.launch(test_game)
        self.assertTrue(ok)
        mock_launch_thread.assert_called_once()
        _, kwargs = mock_launch_thread.call_args
        self.assertTrue(kwargs["is_rom"])
        self.assertEqual(kwargs["system_id"], "snes")
        self.assertEqual(kwargs["emulator_path"], "C:/Emus/snes9x.exe")


if __name__ == "__main__":
    unittest.main(verbosity=2)
