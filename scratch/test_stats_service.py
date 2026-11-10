"""
Unit tests for Advanced Game Statistics, Activity Chart, and Local Goals/Notes.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import json
import tempfile
import time
from datetime import datetime, timedelta

from core.stats_service import (
    format_playtime_minutes,
    format_relative_timestamp,
    format_date_simple,
    get_game_stats,
    add_goal_to_game,
    toggle_game_goal,
    delete_game_goal,
    set_game_notes,
    record_daily_playtime,
    increment_game_play_count
)
from core.config import record_game_session, save_games_data, load_games_data


class TestStatsService(unittest.TestCase):

    def test_01_format_playtime_minutes(self):
        self.assertEqual(format_playtime_minutes(0), "0 min")
        self.assertEqual(format_playtime_minutes(15), "15 min")
        self.assertEqual(format_playtime_minutes(60), "1h")
        self.assertEqual(format_playtime_minutes(75), "1h 15m")
        self.assertEqual(format_playtime_minutes(150), "2h 30m")
        self.assertEqual(format_playtime_minutes(-5), "0 min")

    def test_02_format_relative_timestamp(self):
        self.assertEqual(format_relative_timestamp(None), "Nunca")
        self.assertEqual(format_relative_timestamp(""), "Nunca")

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d 14:30")
        self.assertIn("Hoy", format_relative_timestamp(today_str))

        yesterday = now - timedelta(days=1)
        yesterday_str = yesterday.strftime("%Y-%m-%d 10:00")
        self.assertIn("Ayer", format_relative_timestamp(yesterday_str))

        three_days = now - timedelta(days=3)
        three_days_str = three_days.strftime("%Y-%m-%d 18:00")
        self.assertIn("Hace 3 días", format_relative_timestamp(three_days_str))

    def test_03_get_game_stats_calculation(self):
        game = {
            "name": "Elden Ring",
            "path": "C:\\Games\\EldenRing\\eldenring.exe",
            "playtime_minutes": 180,
            "play_count": 3,
            "daily_playtime": {
                datetime.now().strftime("%Y-%m-%d"): 60,
                (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"): 120
            },
            "goals": [
                {"id": "g1", "text": "Derrotar a Margit", "completed": True},
                {"id": "g2", "text": "Derrotar a Godrick", "completed": False}
            ],
            "notes": "Usar build de destreza con katanas."
        }

        stats = get_game_stats(game)
        self.assertEqual(stats["name"], "Elden Ring")
        self.assertEqual(stats["total_playtime_minutes"], 180)
        self.assertEqual(stats["total_playtime_formatted"], "3h")
        self.assertEqual(stats["play_count"], 3)
        self.assertEqual(stats["avg_session_minutes"], 60)
        self.assertEqual(stats["avg_session_formatted"], "60 min / partida")

        # Actividad semanal: 7 días
        self.assertEqual(len(stats["weekly_activity"]), 7)
        self.assertEqual(stats["weekly_total_minutes"], 180)

        # Actividad mensual: 30 días
        self.assertEqual(len(stats["monthly_activity"]), 30)
        self.assertEqual(stats["monthly_total_minutes"], 180)

        # Metas
        self.assertEqual(stats["goals_total_count"], 2)
        self.assertEqual(stats["goals_completed_count"], 1)
        self.assertEqual(stats["completion_percentage"], 50)
        self.assertEqual(stats["notes"], "Usar build de destreza con katanas.")

    def test_04_goal_management(self):
        game = {"name": "Hollow Knight", "goals": []}

        # Añadir metas
        g1 = add_goal_to_game(game, "Conseguir Capa de Ala de Polilla")
        self.assertIsNotNone(g1)
        self.assertEqual(len(game["goals"]), 1)
        self.assertFalse(g1["completed"])

        g2 = add_goal_to_game(game, "Derrotar a los Señores de las Mantis")
        self.assertEqual(len(game["goals"]), 2)

        # Alternar completado
        ok = toggle_game_goal(game, g1["id"])
        self.assertTrue(ok)
        self.assertTrue(game["goals"][0]["completed"])

        # Eliminar meta
        deleted = delete_game_goal(game, g2["id"])
        self.assertTrue(deleted)
        self.assertEqual(len(game["goals"]), 1)
        self.assertEqual(game["goals"][0]["id"], g1["id"])

    def test_05_notes_management(self):
        game = {"name": "Resident Evil"}
        set_game_notes(game, "Código de caja fuerte despacho: 09-18-27")
        self.assertEqual(game["notes"], "Código de caja fuerte despacho: 09-18-27")

    def test_06_daily_playtime_and_play_count(self):
        game = {"name": "Doom Eternal", "play_count": 2, "daily_playtime": {}}
        increment_game_play_count(game)
        self.assertEqual(game["play_count"], 3)
        self.assertIsNotNone(game.get("date_added"))

        today_str = datetime.now().strftime("%Y-%m-%d")
        record_daily_playtime(game, 45, date_str=today_str)
        record_daily_playtime(game, 30, date_str=today_str)
        self.assertEqual(game["daily_playtime"][today_str], 75)

    def test_07_record_game_session_and_merge_atomic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_config_file = os.path.join(tmpdir, "games.json")
            with patch("core.config.CONFIG_FILE", test_config_file):
                initial_games = [
                    {
                        "name": "Zelda",
                        "path": os.path.join(tmpdir, "zelda.exe"),
                        "playtime_minutes": 30,
                        "play_count": 1,
                        "date_added": "2026-11-01",
                        "goals": [{"id": "z1", "text": "Obtener espada", "completed": False}],
                        "notes": "Hablar con el sabio"
                    }
                ]
                save_games_data(initial_games, merge_existing_playtime=False)

                # Simular sesión de 25 minutos (1500 segundos)
                ok = record_game_session(initial_games[0]["path"], 1500.0)
                self.assertTrue(ok)

                # Verificar actualización atómica
                reloaded = load_games_data()
                self.assertEqual(len(reloaded), 1)
                g = reloaded[0]
                self.assertEqual(g["playtime_minutes"], 55)  # 30 + 25
                self.assertEqual(g["play_count"], 2)  # 1 + 1
                today_k = datetime.now().strftime("%Y-%m-%d")
                self.assertEqual(g["daily_playtime"][today_k], 25)
                self.assertEqual(g["goals"][0]["text"], "Obtener espada")

                # Verificar que save_games_data con merge no borra metas ni historial diario
                mem_games = [
                    {
                        "name": "Zelda",
                        "path": os.path.join(tmpdir, "zelda.exe"),
                        "playtime_minutes": 10,  # menor en memoria
                        "cover": "zelda.png"
                    }
                ]
                save_games_data(mem_games, merge_existing_playtime=True)
                reloaded2 = load_games_data()
                self.assertEqual(reloaded2[0]["playtime_minutes"], 55)
                self.assertEqual(reloaded2[0]["play_count"], 2)
                self.assertEqual(len(reloaded2[0]["goals"]), 1)
                self.assertEqual(reloaded2[0]["notes"], "Hablar con el sabio")

    def test_08_game_stats_dialog_gamepad_navigation(self):
        from ui.dialogs.game_stats_dialog import GameStatsDialog

        # Instanciar mediante __new__ para omitir UI Tkinter en entorno sin display
        dlg = GameStatsDialog.__new__(GameStatsDialog)
        dlg.current_tab = 0
        dlg.chart_mode = "weekly"
        dlg.selected_goal_idx = 0
        dlg.stats = {
            "goals": [
                {"id": "1", "text": "Meta A", "completed": False},
                {"id": "2", "text": "Meta B", "completed": True}
            ]
        }
        dlg.game = {"goals": dlg.stats["goals"], "notes": "Notas test"}

        # Mock de métodos UI
        dlg._switch_tab = MagicMock()
        dlg._set_chart_mode = MagicMock()
        dlg._highlight_selected_goal = MagicMock()
        dlg._toggle_goal = MagicMock()
        dlg._prompt_add_goal = MagicMock()
        dlg._delete_selected_goal = MagicMock()
        dlg._save_notes = MagicMock()
        dlg._prompt_edit_notes_osk = MagicMock()
        dlg.close = MagicMock()

        # 1. Pestañas con LB / RB
        dlg.handle_gamepad_input({"rb": True}, {})
        dlg._switch_tab.assert_called_with(1)

        dlg.handle_gamepad_input({"lb": True}, {})
        dlg._switch_tab.assert_called_with(2)

        # 2. Pestaña 0: Left / Right cambia modo de gráfica
        dlg.current_tab = 0
        dlg.handle_gamepad_input({"left": True}, {})
        dlg._set_chart_mode.assert_called_with("weekly")
        dlg.handle_gamepad_input({"right": True}, {})
        dlg._set_chart_mode.assert_called_with("monthly")

        # 3. Pestaña 1: Up / Down / A / X / Y
        dlg.current_tab = 1
        dlg.handle_gamepad_input({"down": True}, {})
        self.assertEqual(dlg.selected_goal_idx, 1)

        dlg.handle_gamepad_input({"a": True}, {})
        dlg._toggle_goal.assert_called_with("2")

        dlg.handle_gamepad_input({"x": True}, {})
        dlg._prompt_add_goal.assert_called_once()

        dlg.handle_gamepad_input({"y": True}, {})
        dlg._delete_selected_goal.assert_called_once()

        # 4. Botón B cierra
        dlg.handle_gamepad_input({"b": True}, {})
        dlg.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
