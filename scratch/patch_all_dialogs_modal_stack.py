import os

def patch_file(path, patches):
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()
    for target, repl in patches:
        if target not in c:
            print(f"Skipping or not found in {path}: {target[:60]}")
            continue
        c = c.replace(target, repl, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print(f"Patched {path}")

# 3. ui/dialogs/add_edit_game.py
p3_target1 = """from ui.controller_hud import get_button_icon_ctk"""
p3_repl1 = """from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack"""

p3_target2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))"""
p3_repl2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)"""

p3_target3 = """    def destroy(self):
        self._cleanup_temp_preview()"""
p3_repl3 = """    def destroy(self):
        unregister_modal_stack(self)
        self._cleanup_temp_preview()"""

patch_file("ui/dialogs/add_edit_game.py", [
    (p3_target1, p3_repl1),
    (p3_target2, p3_repl2),
    (p3_target3, p3_repl3)
])

# 4. ui/dialogs/gamepad_config_dialog.py
p4_target1 = """from ui.controller_hud import get_button_icon_ctk"""
p4_repl1 = """from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack"""

p4_target2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))"""
p4_repl2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)"""

p4_target3 = """    def close(self):
        self.destroy()"""
p4_repl3 = """    def destroy(self):
        unregister_modal_stack(self)
        super().destroy()

    def close(self):
        self.destroy()"""

patch_file("ui/dialogs/gamepad_config_dialog.py", [
    (p4_target1, p4_repl1),
    (p4_target2, p4_repl2),
    (p4_target3, p4_repl3)
])

# 5. ui/dialogs/scan_results.py
p5_target1 = """from ui.controller_hud import get_button_icon_ctk"""
p5_repl1 = """from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack"""

p5_target2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))"""
p5_repl2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)"""

p5_target3 = """    def close(self):
        self.destroy()"""
p5_repl3 = """    def destroy(self):
        unregister_modal_stack(self)
        super().destroy()

    def close(self):
        self.destroy()"""

patch_file("ui/dialogs/scan_results.py", [
    (p5_target1, p5_repl1),
    (p5_target2, p5_repl2),
    (p5_target3, p5_repl3)
])

# 6. ui/dialogs/select_game_to_edit.py
p6_target1 = """from ui.controller_hud import get_button_icon_ctk"""
p6_repl1 = """from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack"""

p6_target2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))"""
p6_repl2 = """        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)"""

p6_target3 = """    def close(self):
        self.destroy()"""
p6_repl3 = """    def destroy(self):
        unregister_modal_stack(self)
        super().destroy()

    def close(self):
        self.destroy()"""

patch_file("ui/dialogs/select_game_to_edit.py", [
    (p6_target1, p6_repl1),
    (p6_target2, p6_repl2),
    (p6_target3, p6_repl3)
])

print("Completed patching all dialogs for modal stack!")
