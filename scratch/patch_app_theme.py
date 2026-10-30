with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_BG_DARK, COLOR_BG_CANVAS, COLOR_TRANS_KEY,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    font_title, font_button, font_body
)"""

import_rep = """from ui.theme import (
    COLOR_BG_DARK, COLOR_BG_CANVAS, COLOR_BG_CARD, COLOR_TRANS_KEY,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING, COLOR_STATUS_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_title, font_button, font_body
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('fg_color="#141722",\n            hover_color="#242a3a",\n            border_color="#2b3345"',
     'fg_color=COLOR_BG_CARD,\n            hover_color=COLOR_GLASS_HOVER,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('text_color="#64748b"', 'text_color=COLOR_TEXT_DIM'),
    ('text_color="#ffffff"', 'text_color=COLOR_TEXT_WHITE'),
    ('text_color="#94a3b8"', 'text_color=COLOR_TEXT_MUTED'),
    ('text_color="#38bdf8"', 'text_color=COLOR_CYAN_ACCENT'),
    ('t_color = "#ff2d55"', 't_color = COLOR_STATUS_DANGER'),
    ('t_color = "#ff9500"', 't_color = COLOR_STATUS_WARNING'),
    ('t_color = "#007aff"', 't_color = COLOR_IOS_BLUE'),
    ('t_color = "#34c759"', 't_color = COLOR_STATUS_SUCCESS'),
    ('t_color = "#64748b"', 't_color = COLOR_TEXT_DIM'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("app.py patched with theme tokens successfully!")
