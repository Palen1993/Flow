with open('ui/dialogs/cover_picker_dialog.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = """        if inputs.get("x", False) and not prev_inputs.get("x", False):
            try:
                self.entry_search.focus_set()
                self.entry_search.select_range(0, tk.END)
            except Exception:
                pass
            return True"""

replacement = """        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self._open_search_keyboard()
            return True"""

helper = """    def _open_search_keyboard(self):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(val: str):
            try:
                self.entry_search.delete(0, tk.END)
                self.entry_search.insert(0, val)
                self._on_search_button_clicked()
            except Exception:
                pass
        prompt_on_screen_keyboard(self, title="Buscar Carátula o Wallpaper", initial_text=self.entry_search.get(), on_confirm=_on_confirm)

"""

c_n = c.replace('\r\n', '\n')
target_n = target.replace('\r\n', '\n')
replacement_n = replacement.replace('\r\n', '\n')

if target_n in c_n:
    c_n = c_n.replace(target_n, replacement_n)
    # Inject helper before handle_gamepad_input
    if "def handle_gamepad_input(self" in c_n:
        c_n = c_n.replace("    def handle_gamepad_input(self", helper + "    def handle_gamepad_input(self")
    with open('ui/dialogs/cover_picker_dialog.py', 'w', encoding='utf-8') as f:
        f.write(c_n)
    print("SUCCESS: cover_picker_dialog.py patched with search OSK!")
else:
    print("ERROR: target not found in cover_picker_dialog.py")
