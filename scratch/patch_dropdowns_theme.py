with open('ui/dropdowns.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_DROPDOWN, COLOR_CYAN_ACCENT,
    COLOR_CYAN_BORDER, font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_DROPDOWN, COLOR_BG_ITEM_HOVER,
    COLOR_GLASS_BORDER,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MAIN,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('fg_color="#141722",\n            border_color="#2b3345"', 'fg_color=COLOR_BG_CARD,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f1f5f9"', 'text_color=COLOR_TEXT_BRIGHT'),
    ('text_color="#ffffff"', 'text_color=COLOR_TEXT_WHITE'),
    ('hover_color="#222838"', 'hover_color=COLOR_BG_ITEM_HOVER'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dropdowns.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("dropdowns.py patched successfully!")
