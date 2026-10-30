import os
import re

app_path = "app.py"
with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. __init__ additions
target_init = """        self.games = self.load_games()
        self.monitors = get_monitors()
        self.selected_index = 0
        self.is_fullscreen = False
        self.is_mini_mode = False
        self.is_minimized = False
        self.exit_dialog = None
        self.gamepad_config = load_gamepad_config()
        self.protocol("WM_DELETE_WINDOW", self.open_exit_dialog)"""

replacement_init = """        self._games_file_mtime = get_games_file_mtime()
        self.games = self.load_games()
        self.monitors = get_monitors()
        self.selected_index = 0
        self.is_fullscreen = False
        self.is_mini_mode = False
        self.is_minimized = False
        self.exit_dialog = None
        self.gamepad_config = load_gamepad_config()
        self.protocol("WM_DELETE_WINDOW", self.open_exit_dialog)
        self.bind("<FocusIn>", lambda e: self.refresh_games_from_disk_if_modified() if e.widget == self else None)"""

assert target_init in content, "target_init not found"
content = content.replace(target_init, replacement_init, 1)

# 2. load_games & save_games & refresh_games_from_disk_if_modified
target_games_funcs = """    def load_games(self) -> List[Dict[str, Any]]:
        games = load_games_data()
        for g in games:
            resolve_game_cover(g)
        return games

    def save_games(self):
        save_games_data(self.games)"""

replacement_games_funcs = """    def load_games(self) -> List[Dict[str, Any]]:
        games = load_games_data()
        for g in games:
            resolve_game_cover(g)
        self._games_file_mtime = get_games_file_mtime()
        return games

    def save_games(self):
        save_games_data(self.games)
        self._games_file_mtime = get_games_file_mtime()

    def refresh_games_from_disk_if_modified(self) -> bool:
        \"\"\"
        Comprueba si games.json ha sido modificado externamente (por el centinela o sincronización).
        Si es así, recarga y actualiza los metadatos (playtime, last_played) en self.games
        sin reiniciar la posición ni la selección del usuario en el Cover Flow.
        \"\"\"
        try:
            current_mtime = get_games_file_mtime()
            if current_mtime <= getattr(self, "_games_file_mtime", 0.0):
                return False

            fresh_games = load_games_data()
            if not fresh_games:
                return False

            self._games_file_mtime = current_mtime
            fresh_by_path = {}
            fresh_by_name = {}
            for fg in fresh_games:
                resolve_game_cover(fg)
                p = fg.get("path")
                if p:
                    fresh_by_path[os.path.normcase(os.path.normpath(p))] = fg
                n = fg.get("name", "").strip().lower()
                if n:
                    fresh_by_name[n] = fg

            for g in self.games:
                gp = g.get("path")
                norm_p = os.path.normcase(os.path.normpath(gp)) if gp else ""
                fg = fresh_by_path.get(norm_p) or fresh_by_name.get(g.get("name", "").strip().lower())
                if fg:
                    g["playtime_minutes"] = fg.get("playtime_minutes", g.get("playtime_minutes", 0))
                    g["last_played"] = fg.get("last_played", g.get("last_played"))

            self.update_ui_details(self.selected_index)
            return True
        except Exception as e:
            print(f"[App] Error al refrescar juegos desde disco: {e}")
            return False"""

assert target_games_funcs in content, "target_games_funcs not found"
content = content.replace(target_games_funcs, replacement_games_funcs, 1)

# 3. _poll_battery_status polling games refresh
target_poll = """        except Exception:
            pass
        self.after(4000, self._poll_battery_status)"""

replacement_poll = """        except Exception:
            pass
        self.refresh_games_from_disk_if_modified()
        self.after(4000, self._poll_battery_status)"""

assert target_poll in content, "target_poll not found"
content = content.replace(target_poll, replacement_poll, 1)

# 4. restore_window
target_restore = """            # Refrescar metadatos de tiempo de juego si el centinela los actualizó en segundo plano
            self.load_games()
            self.update_ui_details(self.selected_index)"""

replacement_restore = """            # Refrescar metadatos de tiempo de juego si el centinela los actualizó en segundo plano
            self.refresh_games_from_disk_if_modified()"""

assert target_restore in content, "target_restore not found"
content = content.replace(target_restore, replacement_restore, 1)

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

print("app.py successfully patched for playtime sync!")
