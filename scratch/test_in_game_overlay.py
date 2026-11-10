import unittest
from unittest import mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audio_service import (
    get_master_volume,
    set_master_volume,
    change_master_volume,
    toggle_mute
)
from core.active_game_tracker import (
    get_running_game,
    is_game_running,
    terminate_running_game,
    focus_running_game
)

class TestInGameOverlayAndAudio(unittest.TestCase):
    def test_audio_service_volume_and_mute(self):
        # Establecer volumen al 80%
        vol = set_master_volume(80)
        self.assertEqual(vol, 80)

        cur_vol, is_muted = get_master_volume()
        self.assertEqual(cur_vol, 80)

        # Ajuste relativo
        new_vol = change_master_volume(-10)
        self.assertEqual(new_vol, 70)

        # Mute toggle
        prev_muted = is_muted
        new_muted = toggle_mute()
        self.assertEqual(new_muted, not prev_muted)

        # Desmutear
        unmuted = toggle_mute()
        self.assertEqual(unmuted, prev_muted)

    def test_audio_service_bounds(self):
        # Límite superior
        v_high = set_master_volume(150)
        self.assertEqual(v_high, 100)

        # Límite inferior
        v_low = set_master_volume(-50)
        self.assertEqual(v_low, 0)

    @mock.patch("core.active_game_tracker.psutil.process_iter")
    @mock.patch("core.active_game_tracker.load_games_data")
    def test_active_game_tracker_detection(self, mock_load_games, mock_proc_iter):
        # Simular que hay un juego de la biblioteca ejecutándose
        mock_load_games.return_value = [
            {"name": "Hollow Knight", "path": "C:\\Games\\HollowKnight\\hollow_knight.exe"}
        ]

        mock_proc = mock.MagicMock()
        mock_proc.pid = 4567
        mock_proc.info = {"pid": 4567, "name": "hollow_knight.exe", "exe": "C:\\Games\\HollowKnight\\hollow_knight.exe"}

        mock_proc_iter.return_value = [mock_proc]

        game_info = get_running_game()
        self.assertIsNotNone(game_info)
        self.assertEqual(game_info["name"], "Hollow Knight")
        self.assertEqual(game_info["pid"], 4567)
        self.assertTrue(is_game_running())

    @mock.patch("core.active_game_tracker.psutil.process_iter")
    @mock.patch("core.active_game_tracker.load_games_data")
    def test_active_game_tracker_none_running(self, mock_load_games, mock_proc_iter):
        mock_load_games.return_value = [
            {"name": "Elden Ring", "path": "C:\\Games\\eldenring.exe"}
        ]
        mock_proc_iter.return_value = []

        game_info = get_running_game()
        self.assertIsNone(game_info)
        self.assertFalse(is_game_running())

    def test_overlay_dialog_logic(self):
        from ui.dialogs.in_game_overlay import InGameOverlayDialog

        overlay = InGameOverlayDialog.__new__(InGameOverlayDialog)
        overlay.running_game = {"name": "Test Game", "pid": 1234}
        overlay.on_resume_cb = mock.MagicMock()
        overlay.on_return_to_launcher_cb = mock.MagicMock()
        overlay.on_exit_game_cb = mock.MagicMock()
        overlay.destroy = mock.MagicMock()

        # Probar reanudar
        overlay.resume_game()
        overlay.on_resume_cb.assert_called_once()
        overlay.destroy.assert_called_once()

        # Probar volver al lanzador
        overlay.destroy.reset_mock()
        overlay.return_to_launcher()
        overlay.on_return_to_launcher_cb.assert_called_once()
        overlay.destroy.assert_called_once()

        # Probar cerrar juego
        overlay.destroy.reset_mock()
        overlay.terminate_game()
        overlay.on_exit_game_cb.assert_called_once()
        overlay.destroy.assert_called_once()

if __name__ == "__main__":
    unittest.main()
