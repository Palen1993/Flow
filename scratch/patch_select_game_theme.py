with open('ui/dialogs/select_game_to_edit.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_CYAN_ACCENT,
    COLOR_CYAN_BORDER, font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER,
    COLOR_BTN_SECONDARY_BG,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('self.configure(fg_color="#141722")', 'self.configure(fg_color=COLOR_BG_CARD)'),
    ('fg_color="#141722",\n            border_color="#2b3345"', 'fg_color=COLOR_BG_CARD,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('font=font_body(12), text_color="#007aff"', 'font=font_body(12), text_color=COLOR_IOS_BLUE'),
    ('font=font_body(12), text_color="#64748b"', 'font=font_body(12), text_color=COLOR_TEXT_DIM'),
    ('fg_color="#181d28",\n            corner_radius=16,\n            border_color="#242c3d"',
     'fg_color=COLOR_BG_CARD_SECONDARY,\n            corner_radius=16,\n            border_color=COLOR_BORDER_CARD'),
    ('text_color="#f1f5f9",\n            fg_color="#007aff",\n            hover_color="#0062cc"',
     'text_color=COLOR_TEXT_BRIGHT,\n            fg_color=COLOR_IOS_BLUE,\n            hover_color=COLOR_IOS_BLUE_HOVER'),
    ('text_color="#94a3b8"', 'text_color=COLOR_TEXT_MUTED'),
    ('fg_color="#0f1218", border_color="#2b3345"', 'fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_BORDER'),
    ('placeholder_text_color="#64748b"', 'placeholder_text_color=COLOR_TEXT_DIM'),
    ('fg_color="#1c212d", hover_color="#262d3d",\n            border_color="#2b3345"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",\n            border_color=COLOR_GLASS_BORDER'),
    ('card = ctk.CTkFrame(self.scroll_frame, fg_color="#181d28", corner_radius=14, border_color="#242c3d"',
     'card = ctk.CTkFrame(self.scroll_frame, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=14, border_color=COLOR_BORDER_CARD'),
    ('card.configure(border_color="#007aff", border_width=2.0, fg_color="#1d2536")',
     'card.configure(border_color=COLOR_IOS_BLUE, border_width=2.0, fg_color="#1d2536")'),
    ('card.configure(border_color="#242c3d", border_width=1.0, fg_color="#181d28")',
     'card.configure(border_color=COLOR_BORDER_CARD, border_width=1.0, fg_color=COLOR_BG_CARD_SECONDARY)'),
    ('fg_color="#007aff", hover_color="#0062cc",\n            corner_radius=16, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,\n            corner_radius=16, text_color=COLOR_TEXT_WHITE'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/select_game_to_edit.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("select_game_to_edit.py patched successfully!")
