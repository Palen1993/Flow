def patch_file(path, patches):
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()
    for target, repl in patches:
        assert target in c, f"Target not found in {path}"
        c = c.replace(target, repl, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print(f"Patched {path}")

# 1. gamepad_config_dialog.py
patch_file("ui/dialogs/gamepad_config_dialog.py", [
    ("    def destroy(self):\n", "    def destroy(self):\n        unregister_modal_stack(self)\n")
])

# 2. scan_results.py
patch_file("ui/dialogs/scan_results.py", [
    ("    def destroy(self):\n", "    def destroy(self):\n        unregister_modal_stack(self)\n")
])

# 3. select_game_to_edit.py
patch_file("ui/dialogs/select_game_to_edit.py", [
    ("    def destroy(self):\n", "    def destroy(self):\n        unregister_modal_stack(self)\n")
])

print("All destroy methods patched with unregister_modal_stack!")
