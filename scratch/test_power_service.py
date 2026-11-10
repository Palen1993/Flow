"""
Tests unitarios para el servicio de Modos de Energía y Perfiles de Rendimiento (Handheld Mode)
y sus diálogos/overlay asociados.
"""

import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Asegurar path al proyecto
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.power_service import (
    get_device_model_info,
    get_system_battery_status,
    get_current_power_mode,
    set_power_mode,
    apply_game_performance_profile,
    restore_previous_performance_profile,
    POWER_PROFILES,
    GUID_POWER_SAVER,
    GUID_BALANCED,
    GUID_HIGH_PERFORMANCE
)


class TestPowerService(unittest.TestCase):

    def setUp(self):
        # Restablecer modo inicial a equilibrado
        set_power_mode("balanced")

    def test_power_profiles_constants(self):
        """Verifica que los 3 perfiles requeridos existan con sus metadatos."""
        self.assertIn("eco", POWER_PROFILES)
        self.assertIn("balanced", POWER_PROFILES)
        self.assertIn("turbo", POWER_PROFILES)

        eco = POWER_PROFILES["eco"]
        self.assertEqual(eco["guid"], GUID_POWER_SAVER)
        self.assertIn("~9W", eco["tdp_target"])

        bal = POWER_PROFILES["balanced"]
        self.assertEqual(bal["guid"], GUID_BALANCED)

        turbo = POWER_PROFILES["turbo"]
        self.assertEqual(turbo["guid"], GUID_HIGH_PERFORMANCE)

    def test_device_model_detection_rog_ally(self):
        """Prueba detección de ASUS ROG Ally mediante firmas de fabricante y producto."""
        with patch("core.power_service.is_windows", return_value=True):
            with patch("core.power_service.winreg") as mock_reg:
                mock_reg.HKEY_LOCAL_MACHINE = 1
                mock_reg.KEY_READ = 1

                def fake_open_key(root, subkey):
                    return MagicMock()

                def fake_query_val(key, val_name):
                    vals = {
                        "SystemManufacturer": ("ASUSTeK COMPUTER INC.", 1),
                        "SystemProductName": ("ROG Ally RC71L_RC71L", 1),
                        "BaseBoardProduct": ("RC71L", 1)
                    }
                    return vals.get(val_name, ("", 1))

                mock_reg.OpenKey.side_effect = fake_open_key
                mock_reg.QueryValueEx.side_effect = fake_query_val

                info = get_device_model_info()
                self.assertTrue(info["is_handheld"])
                self.assertEqual(info["badge"], "ROG Ally")
                self.assertIn("ROG Ally", info["display_name"])

    def test_device_model_detection_steam_deck(self):
        """Prueba detección de Steam Deck con Windows instalado."""
        with patch("core.power_service.is_windows", return_value=True):
            with patch("core.power_service.winreg") as mock_reg:
                mock_reg.HKEY_LOCAL_MACHINE = 1
                mock_reg.KEY_READ = 1

                def fake_query_val(key, val_name):
                    vals = {
                        "SystemManufacturer": ("Valve", 1),
                        "SystemProductName": ("Jupiter", 1),
                        "BaseBoardProduct": ("Jupiter", 1)
                    }
                    return vals.get(val_name, ("", 1))

                mock_reg.OpenKey.return_value = MagicMock()
                mock_reg.QueryValueEx.side_effect = fake_query_val

                info = get_device_model_info()
                self.assertTrue(info["is_handheld"])
                self.assertEqual(info["badge"], "Steam Deck")

    def test_device_model_detection_legion_go(self):
        """Prueba detección de Lenovo Legion Go."""
        with patch("core.power_service.is_windows", return_value=True):
            with patch("core.power_service.winreg") as mock_reg:
                mock_reg.HKEY_LOCAL_MACHINE = 1
                mock_reg.KEY_READ = 1

                def fake_query_val(key, val_name):
                    vals = {
                        "SystemManufacturer": ("LENOVO", 1),
                        "SystemProductName": ("83E1 (Legion Go 8APU1)", 1),
                        "BaseBoardProduct": ("LNVNB161216", 1)
                    }
                    return vals.get(val_name, ("", 1))

                mock_reg.OpenKey.return_value = MagicMock()
                mock_reg.QueryValueEx.side_effect = fake_query_val

                info = get_device_model_info()
                self.assertTrue(info["is_handheld"])
                self.assertEqual(info["badge"], "Legion Go")

    def test_battery_status_structure(self):
        """Verifica la estructura y campos de get_system_battery_status."""
        bat = get_system_battery_status()
        self.assertIsInstance(bat, dict)
        self.assertIn("has_battery", bat)
        self.assertIn("ac_connected", bat)
        self.assertIn("percent", bat)
        self.assertIn("status_label", bat)
        self.assertIn("icon", bat)

    def test_set_and_get_power_mode(self):
        """Prueba cambio y consulta de perfiles de energía."""
        res_eco = set_power_mode("eco")
        self.assertTrue(res_eco)
        self.assertEqual(get_current_power_mode(), "eco")

        res_turbo = set_power_mode("turbo")
        self.assertTrue(res_turbo)
        self.assertEqual(get_current_power_mode(), "turbo")

        res_bal = set_power_mode("balanced")
        self.assertTrue(res_bal)
        self.assertEqual(get_current_power_mode(), "balanced")

        # Modo no válido -> fallback a balanced
        set_power_mode("invalid_mode")
        self.assertEqual(get_current_power_mode(), "balanced")

    def test_per_game_profile_application_and_restore(self):
        """Prueba asignación automática de perfil al juego y restauración al terminar."""
        set_power_mode("balanced")

        # Juego sin perfil específico ("default")
        game_default = {"name": "Indie Game", "performance_mode": "default"}
        prev = apply_game_performance_profile(game_default)
        self.assertIsNone(prev)
        self.assertEqual(get_current_power_mode(), "balanced")

        # Juego con perfil turbo
        game_aaa = {"name": "Cyberpunk 2077", "performance_mode": "turbo"}
        prev = apply_game_performance_profile(game_aaa)
        self.assertEqual(prev, "balanced")
        self.assertEqual(get_current_power_mode(), "turbo")

        # Restaurar
        restore_previous_performance_profile()
        self.assertEqual(get_current_power_mode(), "balanced")

        # Juego con perfil eco
        game_retro = {"name": "Celeste", "performance_mode": "eco"}
        prev = apply_game_performance_profile(game_retro)
        self.assertEqual(prev, "balanced")
        self.assertEqual(get_current_power_mode(), "eco")

        # Restaurar
        restore_previous_performance_profile()
        self.assertEqual(get_current_power_mode(), "balanced")


class TestOverlayPowerCycle(unittest.TestCase):

    def test_overlay_power_cycling(self):
        """Verifica que el método cycle_overlay_power_mode alterne secuencialmente."""
        from ui.dialogs.in_game_overlay import InGameOverlayDialog

        overlay = InGameOverlayDialog.__new__(InGameOverlayDialog)
        overlay.current_overlay_power_mode = "balanced"
        overlay._power_mode_buttons = {}
        overlay.set_overlay_power_mode = MagicMock(side_effect=lambda m: setattr(overlay, "current_overlay_power_mode", m))

        overlay.cycle_overlay_power_mode()
        self.assertEqual(overlay.current_overlay_power_mode, "turbo")

        overlay.cycle_overlay_power_mode()
        self.assertEqual(overlay.current_overlay_power_mode, "eco")

        overlay.cycle_overlay_power_mode()
        self.assertEqual(overlay.current_overlay_power_mode, "balanced")

    def test_overlay_gamepad_x_button_cycles_power(self):
        """Verifica que presionar el botón X en el overlay ejecute el cambio de perfil."""
        from ui.dialogs.in_game_overlay import InGameOverlayDialog

        overlay = InGameOverlayDialog.__new__(InGameOverlayDialog)
        overlay.cycle_overlay_power_mode = MagicMock()
        overlay.resume_game = MagicMock()
        overlay.toggle_volume_mute = MagicMock()

        # Pulso de botón X (pressed=True, prev=False)
        overlay.handle_gamepad_input({"x": True}, {"x": False})
        overlay.cycle_overlay_power_mode.assert_called_once()


class TestPerformanceDialogNavigation(unittest.TestCase):

    def test_performance_dialog_gamepad_actions(self):
        """Prueba la navegación y pulsaciones en PerformanceProfileDialog."""
        from ui.dialogs.performance_dialog import PerformanceProfileDialog

        dialog = PerformanceProfileDialog.__new__(PerformanceProfileDialog)
        dialog.selected_profile_idx = 1
        dialog.game = {"name": "Test RPG", "performance_mode": "default"}
        dialog.game_mode = "default"
        dialog.on_game_updated = MagicMock()
        dialog._is_active = True
        dialog._highlight_selected_profile = MagicMock()
        dialog._activate_profile = MagicMock()
        dialog._set_game_profile = MagicMock()
        dialog.close = MagicMock()

        # D-pad derecha
        dialog.handle_gamepad_input({"right": True}, {"right": False})
        self.assertEqual(dialog.selected_profile_idx, 2)

        # D-pad izquierda
        dialog.handle_gamepad_input({"left": True}, {"left": False})
        self.assertEqual(dialog.selected_profile_idx, 1)

        # Botón A
        dialog.handle_gamepad_input({"a": True}, {"a": False})
        dialog._activate_profile.assert_called_once_with("balanced")

        # Botón X
        dialog.handle_gamepad_input({"x": True}, {"x": False})
        dialog._set_game_profile.assert_called_once()

        # Botón B
        dialog.handle_gamepad_input({"b": True}, {"b": False})
        dialog.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
