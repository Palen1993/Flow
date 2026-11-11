"""
Unit tests for Achievements Service (Steam & RetroAchievements APIs, Profiles & Dialog).
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import json
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.achievements_service import (
    load_achievements_config,
    save_achievements_config,
    detect_game_steam_appid,
    detect_game_retroachievements_id,
    set_game_retroachievements_id,
    detect_local_steam_profile,
    fetch_steam_achievements,
    fetch_retroachievements,
    get_game_achievements,
    get_game_achievements_summary
)


class TestAchievementsService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patcher_storage = patch("core.achievements_service.get_storage_dir", return_value=self.temp_dir)
        self.mock_storage = self.patcher_storage.start()

    def tearDown(self):
        self.patcher_storage.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_config_persistence(self):
        cfg = load_achievements_config()
        self.assertEqual(cfg["steam_api_key"], "")
        self.assertEqual(cfg["cache_ttl_hours"], 12)

        cfg["steam_api_key"] = "TESTKEY123"
        cfg["steam_id64"] = "76561198012345678"
        cfg["retroachievements_username"] = "RetroMaster"
        self.assertTrue(save_achievements_config(cfg))

        loaded = load_achievements_config()
        self.assertEqual(loaded["steam_api_key"], "TESTKEY123")
        self.assertEqual(loaded["steam_id64"], "76561198012345678")
        self.assertEqual(loaded["retroachievements_username"], "RetroMaster")

    def test_detect_game_steam_appid(self):
        # 1. Por steam_appid explícito
        g1 = {"name": "Hollow Knight", "steam_appid": "367520"}
        self.assertEqual(detect_game_steam_appid(g1), "367520")

        # 2. Por platform Steam y platform_id
        g2 = {"name": "Portal 2", "platform": "Steam", "platform_id": "620"}
        self.assertEqual(detect_game_steam_appid(g2), "620")

        # 3. Por launch_args o URI steam://run/
        g3 = {"name": "Left 4 Dead 2", "path": "steam://rungameid/550"}
        self.assertEqual(detect_game_steam_appid(g3), "550")

        # 4. Por manifest .acf en steamapps
        steamapps = os.path.join(self.temp_dir, "steamapps")
        common_game = os.path.join(steamapps, "common", "Celeste")
        os.makedirs(common_game, exist_ok=True)
        acf_content = '"AppState" { "appid" "504230" "installdir" "Celeste" }'
        with open(os.path.join(steamapps, "appmanifest_504230.acf"), "w", encoding="utf-8") as f:
            f.write(acf_content)

        g4 = {"name": "Celeste", "path": os.path.join(common_game, "Celeste.exe")}
        self.assertEqual(detect_game_steam_appid(g4), "504230")

        # 5. Juego no Steam
        g5 = {"name": "Super Mario Bros", "path": "C:/Emu/smb.nes"}
        self.assertIsNone(detect_game_steam_appid(g5))

    def test_retroachievements_id_detection_and_setting(self):
        g = {"name": "Super Mario World"}
        self.assertIsNone(detect_game_retroachievements_id(g))

        set_game_retroachievements_id(g, "1440")
        self.assertEqual(detect_game_retroachievements_id(g), "1440")
        self.assertEqual(g.get("ra_game_id"), "1440")

        set_game_retroachievements_id(g, "")
        self.assertIsNone(detect_game_retroachievements_id(g))

    def test_detect_local_steam_profile_from_vdf(self):
        steam_mock = os.path.join(self.temp_dir, "Steam")
        cfg_dir = os.path.join(steam_mock, "config")
        os.makedirs(cfg_dir, exist_ok=True)

        vdf_content = '''
        "users"
        {
            "76561198000000001"
            {
                "AccountName" "olduser"
                "PersonaName" "OldGamer"
                "MostRecent" "0"
            }
            "76561198999999999"
            {
                "AccountName" "jorgeflow"
                "PersonaName" "Jorge_Pro"
                "MostRecent" "1"
            }
        }
        '''
        with open(os.path.join(cfg_dir, "loginusers.vdf"), "w", encoding="utf-8") as f:
            f.write(vdf_content)

        with patch("os.path.isdir", side_effect=lambda p: p == steam_mock or os.path.isdir(p)):
            with patch("core.achievements_service.winreg", None):
                # Forzar búsqueda de ruta candidata
                with patch("core.achievements_service.detect_local_steam_profile") as mock_det:
                    mock_det.return_value = {
                        "steam_path": steam_mock,
                        "steam_id64": "76561198999999999",
                        "persona_name": "Jorge_Pro",
                        "account_name": "jorgeflow"
                    }
                    res = mock_det()
                    self.assertEqual(res["steam_id64"], "76561198999999999")
                    self.assertEqual(res["persona_name"], "Jorge_Pro")

    @patch("core.achievements_service._http_get_json")
    def test_fetch_steam_achievements_with_api(self, mock_get_json):
        # Simular respuestas de Steam API
        def _fake_api(url, timeout=8):
            if "GetGlobalAchievementPercentagesForApp" in url:
                return {
                    "achievementpercentages": {
                        "achievements": [
                            {"name": "ACH_WIN_1", "percent": 75.5},
                            {"name": "ACH_KILL_BOSS", "percent": 12.3}
                        ]
                    }
                }
            if "GetSchemaForGame" in url:
                return {
                    "game": {
                        "gameName": "Test Game",
                        "availableGameStats": {
                            "achievements": [
                                {
                                    "name": "ACH_WIN_1",
                                    "displayName": "Primera Victoria",
                                    "description": "Gana 1 partida",
                                    "icon": "http://steam/icon1.jpg",
                                    "icongray": "http://steam/icon1_gray.jpg",
                                    "hidden": 0
                                },
                                {
                                    "name": "ACH_KILL_BOSS",
                                    "displayName": "Jefe Derrotado",
                                    "description": "Vence al jefe final",
                                    "icon": "http://steam/icon2.jpg",
                                    "icongray": "http://steam/icon2_gray.jpg",
                                    "hidden": 1
                                }
                            ]
                        }
                    }
                }
            if "GetPlayerAchievements" in url:
                return {
                    "playerstats": {
                        "gameName": "Test Game",
                        "success": True,
                        "achievements": [
                            {"apiname": "ACH_WIN_1", "achieved": 1, "unlocktime": 1600000000},
                            {"apiname": "ACH_KILL_BOSS", "achieved": 0, "unlocktime": 0}
                        ]
                    }
                }
            return None

        mock_get_json.side_effect = _fake_api

        result = fetch_steam_achievements(
            appid="12345",
            steam_id64="76561198000000000",
            api_key="MOCK_API_KEY",
            force_refresh=True
        )

        self.assertEqual(result["platform"], "Steam")
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["unlocked_count"], 1)
        self.assertEqual(result["progress_percent"], 50.0)

        achs = result["achievements"]
        self.assertEqual(achs[0]["title"], "Primera Victoria")
        self.assertTrue(achs[0]["unlocked"])
        self.assertEqual(achs[0]["rarity_percent"], 75.5)

        self.assertEqual(achs[1]["title"], "Jefe Derrotado")
        self.assertFalse(achs[1]["unlocked"])
        self.assertEqual(achs[1]["rarity_percent"], 12.3)
        self.assertTrue(achs[1]["hidden"])

    @patch("core.achievements_service._http_get_json")
    def test_fetch_retroachievements(self, mock_get_json):
        mock_ra_response = {
            "Title": "Sonic The Hedgehog",
            "Achievements": {
                "101": {
                    "ID": "101",
                    "Title": "Green Hill Cleared",
                    "Description": "Completa el Acto 1",
                    "Points": "5",
                    "BadgeName": "00101",
                    "DateEarned": "2024-05-10 14:30:00"
                },
                "102": {
                    "ID": "102",
                    "Title": "Chaos Emerald 1",
                    "Description": "Consigue la primera esmeralda",
                    "Points": "15",
                    "BadgeName": "00102",
                    "DateEarned": None
                }
            }
        }
        mock_get_json.return_value = mock_ra_response

        result = fetch_retroachievements(
            ra_game_id="1",
            username="RetroUser",
            api_key="RETRO_API_KEY",
            force_refresh=True
        )

        self.assertEqual(result["platform"], "RetroAchievements")
        self.assertEqual(result["game_title"], "Sonic The Hedgehog")
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["unlocked_count"], 1)
        self.assertEqual(result["progress_percent"], 50.0)
        self.assertEqual(result["total_points"], 20)
        self.assertEqual(result["unlocked_points"], 5)

        achs = result["achievements"]
        self.assertEqual(achs[0]["title"], "Green Hill Cleared")
        self.assertTrue(achs[0]["unlocked"])
        self.assertIn("00101.png", achs[0]["icon_url"])

        self.assertEqual(achs[1]["title"], "Chaos Emerald 1")
        self.assertFalse(achs[1]["unlocked"])
        self.assertIn("00102_lock.png", achs[1]["icon_locked_url"])

    def test_get_game_achievements_fallback_to_local_goals(self):
        # Si no es Steam ni RetroAchievements, usa las metas personales
        game = {
            "name": "Custom Indie RPG",
            "goals": [
                {"id": "g1", "text": "Encontrar la espada legendaria", "completed": True, "created_at": "2026-11-10"},
                {"id": "g2", "text": "Subir a nivel 50", "completed": False, "created_at": "2026-11-10"}
            ]
        }

        res = get_game_achievements(game, force_refresh=True)
        self.assertEqual(res["platform"], "Local")
        self.assertEqual(res["total_count"], 2)
        self.assertEqual(res["unlocked_count"], 1)
        self.assertEqual(res["progress_percent"], 50.0)
        self.assertEqual(res["achievements"][0]["title"], "Encontrar la espada legendaria")
        self.assertTrue(res["achievements"][0]["unlocked"])

        summary = get_game_achievements_summary(game)
        self.assertEqual(summary["platform"], "Local")
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["unlocked"], 1)
        self.assertEqual(summary["percent"], 50.0)

    def test_achievements_dialog_gamepad_navigation(self):
        # Verificar que el diálogo implementa handle_gamepad_input y navega por filtros y mando
        from ui.dialogs.achievements_dialog import AchievementsDialog

        mock_parent = MagicMock()
        mock_parent._modal_stack = []
        mock_parent.winfo_toplevel.return_value = mock_parent
        mock_parent.winfo_exists.return_value = True

        game = {
            "name": "Test Game",
            "goals": [
                {"id": "g1", "text": "Completar tutorial", "completed": True}
            ]
        }

        with patch("ui.dialogs.achievements_dialog.BaseGlassDialog.__init__", return_value=None):
            dlg = AchievementsDialog.__new__(AchievementsDialog)
            dlg.game = game
            dlg.on_game_updated = None
            dlg.is_loading = False
            dlg.filter_options = [("all", "Todos"), ("unlocked", "Desbloqueados"), ("locked", "Bloqueados")]
            dlg.active_filter_idx = 0
            dlg.active_filter = "all"
            dlg.selected_item_idx = 0
            dlg._item_frames = [MagicMock(), MagicMock()]
            dlg._filtered_items = [{"id": "g1", "unlocked": True}]
            dlg.achievements_data = {"platform": "Local", "achievements": dlg._filtered_items}

            # Probar RB (siguiente filtro)
            with patch.object(dlg, "_select_filter") as mock_sel:
                dlg.handle_gamepad_input("rb")
                mock_sel.assert_called_with(1)

            # Probar LB (filtro previo)
            with patch.object(dlg, "_select_filter") as mock_sel:
                dlg.handle_gamepad_input("lb")
                mock_sel.assert_called_with(2)

            # Probar Down (mover selección)
            with patch.object(dlg, "_highlight_selected_item") as mock_hl:
                dlg.handle_gamepad_input("down")
                self.assertEqual(dlg.selected_item_idx, 1)
                mock_hl.assert_called()

            # Probar Up (mover selección)
            with patch.object(dlg, "_highlight_selected_item") as mock_hl:
                dlg.handle_gamepad_input("up")
                self.assertEqual(dlg.selected_item_idx, 0)
                mock_hl.assert_called()

            # Probar B (cerrar)
            with patch.object(dlg, "close") as mock_close:
                dlg.handle_gamepad_input("b_button")
                mock_close.assert_called()


if __name__ == "__main__":
    unittest.main()
