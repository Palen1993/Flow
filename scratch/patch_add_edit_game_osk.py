with open('ui/dialogs/add_edit_game.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = """        self._nav_controls = [
            ("btn", self.btn_online, self.download_online_hd_cover),
            ("btn", self.btn_cover, self.browse_cover),
            ("btn", self.btn_autodetect, self.autodetect_cover),
            ("entry", self.name_entry, None),
            ("entry", self.path_entry, None),
            ("btn", self.btn_browse_exe, self.browse_exe),
            ("entry", self.args_entry, None),
            ("dropdown", self.monitor_dropdown, self.monitor_dropdown._toggle_dropdown),
            ("check", self.priority_check, self.priority_check.toggle),
            ("btn", self.btn_save, self.save),
            ("btn", self.btn_cancel, self.destroy),
        ]"""

replacement = """        self._nav_controls = [
            ("btn", self.btn_online, self.download_online_hd_cover),
            ("btn", self.btn_cover, self.browse_cover),
            ("btn", self.btn_autodetect, self.autodetect_cover),
            ("entry", self.name_entry, lambda: self._open_keyboard_for_entry(self.name_entry, "Nombre del Juego")),
            ("entry", self.path_entry, lambda: self._open_keyboard_for_entry(self.path_entry, "Ruta del Ejecutable")),
            ("btn", self.btn_browse_exe, self.browse_exe),
            ("entry", self.args_entry, lambda: self._open_keyboard_for_entry(self.args_entry, "Parámetros de Ejecución")),
            ("dropdown", self.monitor_dropdown, self.monitor_dropdown._toggle_dropdown),
            ("check", self.priority_check, self.priority_check.toggle),
            ("btn", self.btn_save, self.save),
            ("btn", self.btn_cancel, self.destroy),
        ]"""

helper = """    def _open_keyboard_for_entry(self, entry_widget: ctk.CTkEntry, title: str):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(new_val: str):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, new_val)
            if entry_widget == self.path_entry:
                self.auto_fill_name_from_exe()
        prompt_on_screen_keyboard(self, title=title, initial_text=entry_widget.get(), on_confirm=_on_confirm)

"""

c_n = c.replace('\r\n', '\n')
target_n = target.replace('\r\n', '\n')
replacement_n = replacement.replace('\r\n', '\n')

if target_n in c_n:
    c_n = c_n.replace(target_n, replacement_n)
    # Inject helper before save method
    if "def save(self):" in c_n:
        c_n = c_n.replace("    def save(self):", helper + "    def save(self):")
    with open('ui/dialogs/add_edit_game.py', 'w', encoding='utf-8') as f:
        f.write(c_n)
    print("SUCCESS: add_edit_game.py patched with OSK!")
else:
    print("ERROR: target not found in add_edit_game.py")
