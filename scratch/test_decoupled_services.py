import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import io
import unittest
from unittest.mock import patch, MagicMock

from core.library_service import GameLibraryService, format_monitor_label
from core.execution_service import GameExecutionService
from core.cover_downloader import _safe_read_response
from core.config import update_game_fields_atomic, load_games_data


class TestDecoupledServices(unittest.TestCase):
    def test_01_library_service_operations(self):
        lib = GameLibraryService()
        lib.games = [
            {"name": "Alpha", "path": "C:\\Games\\Alpha\\game.exe", "monitor": 0},
            {"name": "Bravo", "path": "C:\\Games\\Bravo\\game.exe", "monitor": 1, "playtime_minutes": 150},
            {"name": "Charlie", "path": "C:\\Games\\Charlie\\game.exe", "monitor": 0}
        ]

        # Test alphabetical jump forward / backward
        idx_fwd = lib.find_alphabetical_jump(current_index=0, direction=1)
        self.assertEqual(idx_fwd, 1)

        idx_char = lib.find_alphabetical_jump(current_index=0, char="c")
        self.assertEqual(idx_char, 2)

        # Test subtitle formatting
        sub = lib.format_subtitle(lib.games[1])
        self.assertIn("2.5 h jugadas", sub)

        # Test in-memory update
        with patch.object(lib, "save"):
            lib.update_game(0, name="Alpha Enhanced", path="C:\\Games\\Alpha\\game.exe", monitor=0, high_priority=True, cover="")
            self.assertEqual(lib.games[0]["name"], "Alpha Enhanced")

            new_idx = lib.delete_game(1)
            self.assertEqual(len(lib.games), 2)
            self.assertEqual(new_idx, 1)

    def test_02_execution_service_concurrency(self):
        svc = GameExecutionService()
        self.assertFalse(svc.is_launching)

        # Mock launch_game_thread to prevent real process launch
        with patch("core.execution_service.launch_game_thread") as mock_launch:
            game = {"name": "TestGame", "path": "C:\\fake.exe"}
            res = svc.launch(game)
            self.assertTrue(res)
            self.assertTrue(svc.is_launching)

            # Second immediate launch must be rejected
            res_rejected = svc.launch(game)
            self.assertFalse(res_rejected)

            svc.reset()
            self.assertFalse(svc.is_launching)

    def test_03_decompression_bomb_protection(self):
        # Normal stream under 15 MB
        normal_data = b"X" * (1024 * 64)
        mock_resp = io.BytesIO(normal_data)
        out = _safe_read_response(mock_resp, max_bytes=1024 * 128)
        self.assertEqual(len(out), 1024 * 64)

        # Stream exceeding limit raises ValueError
        overflow_data = b"Y" * (1024 * 256)
        mock_overflow_resp = io.BytesIO(overflow_data)
        with self.assertRaises(ValueError):
            _safe_read_response(mock_overflow_resp, max_bytes=1024 * 64)

    def test_04_atomic_field_update(self):
        games = load_games_data()
        if games:
            first_game = games[0]
            name = first_game["name"]
            orig_mins = first_game.get("playtime_minutes", 0)

            with patch("core.config.save_games_data", return_value=True) as mock_save:
                res = update_game_fields_atomic(name, {"playtime_minutes": orig_mins})
                self.assertTrue(res)
                mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
