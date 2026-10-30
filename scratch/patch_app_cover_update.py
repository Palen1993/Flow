with open("app.py", "r", encoding="utf-8") as f:
    c = f.read()

target = """                if hasattr(self, "cover_stage") and self.cover_stage:
                    g_key = self.cover_stage._get_key(game)
                    self.cover_stage.raw_jewels.pop(g_key, None)
                    self.cover_stage.flat_covers.pop(g_key, None)
                    self.cover_stage.rendered_cache.pop(g_key, None)
                    self.cover_stage.set_games(self.games, target_index=self.selected_index)"""

repl = """                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.update_game_cover(game)"""

assert target in c, "target not found"
c = c.replace(target, repl, 1)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(c)

print("app.py successfully updated with update_game_cover!")
