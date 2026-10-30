with open('ui/dialogs/select_game_to_edit.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Add button search in footer
footer_target = """        btn_close = ctk.CTkButton(
            footer, text="Cerrar ", image=get_button_icon_ctk("b", size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED,
            font=font_button(12), command=self.destroy
        )
        btn_close.pack(side="right", padx=4, pady=4)"""

footer_rep = """        btn_close = ctk.CTkButton(
            footer, text="Cerrar ", image=get_button_icon_ctk("b", size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED,
            font=font_button(12), command=self.destroy
        )
        btn_close.pack(side="right", padx=4, pady=4)

        btn_search = ctk.CTkButton(
            footer, text="Buscar ", image=get_button_icon_ctk("y", size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED,
            font=font_button(12), command=self._open_search_keyboard
        )
        btn_search.pack(side="right", padx=6, pady=4)"""

gamepad_target = """    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True"""

gamepad_rep = """    def _open_search_keyboard(self):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(val: str):
            self.search_var.set(val)
            self.refresh_list()
        prompt_on_screen_keyboard(self, title="Filtrar Juegos", initial_text=self.search_var.get(), on_confirm=_on_confirm)

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            self._open_search_keyboard()
            return True"""

c_n = c.replace('\r\n', '\n')
footer_target_n = footer_target.replace('\r\n', '\n')
footer_rep_n = footer_rep.replace('\r\n', '\n')
gamepad_target_n = gamepad_target.replace('\r\n', '\n')
gamepad_rep_n = gamepad_rep.replace('\r\n', '\n')

if footer_target_n in c_n and gamepad_target_n in c_n:
    c_n = c_n.replace(footer_target_n, footer_rep_n)
    c_n = c_n.replace(gamepad_target_n, gamepad_rep_n)
    with open('ui/dialogs/select_game_to_edit.py', 'w', encoding='utf-8') as f:
        f.write(c_n)
    print("SUCCESS: select_game_to_edit.py patched with search OSK!")
else:
    print("ERROR: targets not found in select_game_to_edit.py")
