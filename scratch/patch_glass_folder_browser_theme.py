with open('ui/dialogs/glass_folder_browser.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    font_button, font_body, scroll_to_widget,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER
)"""

import_rep = """from ui.theme import (
    font_button, font_body, scroll_to_widget,
    COLOR_BG_CARD, COLOR_BG_DARK, COLOR_GLASS_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_LIGHT, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT,
    COLOR_TEXT_MUTED, COLOR_TEXT_MUTED_LIGHT,
    COLOR_CYAN_ACCENT,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_DANGER, COLOR_BG_INPUT_ACTIVE
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('fg_color="#141722", border_color="#2b3345"', 'fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('text_color="#94a3b8"', 'text_color=COLOR_TEXT_MUTED'),
    ('text_color="#38bdf8"', 'text_color=COLOR_CYAN_ACCENT'),
    ('self.card, fg_color="#0f1218"', 'self.card, fg_color=COLOR_BG_DARK'),
    ('fg_color="#1c212d", hover_color="#283040",\n            border_color="#333c50", border_width=1.0, text_color="#cbd5e1"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER,\n            border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0, text_color=COLOR_TEXT_MUTED_LIGHT'),
    ('text_color="#ffffff"', 'text_color=COLOR_TEXT_WHITE'),
    ('text_color="#f1f5f9"', 'text_color=COLOR_TEXT_BRIGHT'),
    ('text_color="#ff2d55"', 'text_color=COLOR_STATUS_DANGER'),
    ('text_color="#e2e8f0"', 'text_color=COLOR_TEXT_LIGHT'),
    ('fg_color="#242c3d",\n                    border_color="#38bdf8"',
     'fg_color=COLOR_BG_INPUT_ACTIVE,\n                    border_color=COLOR_CYAN_ACCENT'),
    ('border_color="#38bdf8"', 'border_color=COLOR_CYAN_ACCENT'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/glass_folder_browser.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("glass_folder_browser.py patched successfully!")
