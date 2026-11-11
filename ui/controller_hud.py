import math
import re
from typing import Dict, List, Optional, Tuple
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from core.coverflow_engine import prevent_transparency_color_collision
from gamepad_manager import get_connected_controller_family

_ICON_PIL_CACHE: Dict[Tuple[str, str, int], Image.Image] = {}
_ICON_CTK_CACHE: Dict[Tuple[str, str, int], ctk.CTkImage] = {}
_STRIP_CACHE: Dict[Tuple[str, int], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _draw_button_glyph(draw: ImageDraw.ImageDraw, btn_key: str, family: str, cx: int, cy: int, r: int):
    """
    Dibuja un único botón físico real del mando en coordenadas (cx, cy) con radio r (en escala 2x):
      - btn_key in ('a', 'b', 'x', 'y', 'start', 'select', 'lb', 'rb', 'lt', 'rt')
      - family in ('xbox', 'playstation')
    """
    key = btn_key.lower()
    fam = "playstation" if family == "playstation" else "xbox"
    font_letter = _load_font(int(r * 1.24), bold=True)
    font_bumper = _load_font(int(r * 0.88), bold=True)

    if key == "a":
        if fam == "playstation":
            # Botón Cruz (✕) azul de PlayStation
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 32, 54, 255), outline=(56, 189, 248, 255), width=4)
            d = int(r * 0.46)
            draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=(96, 165, 250, 255), width=5)
            draw.line([(cx + d, cy - d), (cx - d, cy + d)], fill=(96, 165, 250, 255), width=5)
        else:
            # Botón (A) verde de Xbox
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 46, 26, 255), outline=(34, 197, 94, 255), width=4)
            draw.text((cx, cy - 1), "A", font=font_letter, fill=(74, 222, 128, 255), anchor="mm")

    elif key == "b":
        if fam == "playstation":
            # Botón Círculo (◯) rojo de PlayStation
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(44, 22, 28, 255), outline=(248, 113, 113, 255), width=4)
            cr = int(r * 0.54)
            draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=(251, 113, 133, 255), width=4)
        else:
            # Botón (B) rojo de Xbox
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(52, 20, 24, 255), outline=(239, 68, 68, 255), width=4)
            draw.text((cx, cy - 1), "B", font=font_letter, fill=(252, 165, 165, 255), anchor="mm")

    elif key == "x":
        if fam == "playstation":
            # Botón Cuadrado (□) rosa/violeta de PlayStation
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(44, 22, 46, 255), outline=(232, 121, 249, 255), width=4)
            sq = int(r * 0.48)
            draw.rectangle([cx - sq, cy - sq, cx + sq, cy + sq], outline=(240, 171, 252, 255), width=4)
        else:
            # Botón (X) azul de Xbox
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(18, 36, 58, 255), outline=(56, 189, 248, 255), width=4)
            draw.text((cx, cy - 1), "X", font=font_letter, fill=(125, 211, 252, 255), anchor="mm")

    elif key == "y":
        if fam == "playstation":
            # Botón Triángulo (△) verde agua de PlayStation
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(20, 36, 42, 255), outline=(45, 212, 191, 255), width=4)
            tr = int(r * 0.58)
            p1 = (cx, cy - tr - 1)
            p2 = (cx - int(tr * 0.90), cy + int(tr * 0.68))
            p3 = (cx + int(tr * 0.90), cy + int(tr * 0.68))
            draw.polygon([p1, p2, p3], outline=(52, 211, 153, 255), width=4)
        else:
            # Botón (Y) amarillo de Xbox
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(46, 36, 14, 255), outline=(250, 204, 21, 255), width=4)
            draw.text((cx, cy - 1), "Y", font=font_letter, fill=(253, 224, 71, 255), anchor="mm")

    elif key == "start":
        if fam == "playstation":
            pw = int(r * 1.15)
            ph = int(r * 1.62)
            draw.rounded_rectangle(
                [cx - pw // 2, cy - ph // 2 + 3, cx + pw // 2, cy + ph // 2 + 3],
                radius=pw // 2,
                fill=(32, 40, 56, 255),
                outline=(56, 189, 248, 255),
                width=3
            )
            bw = int(r * 0.82)
            for dy in (-int(r * 0.92), -int(r * 0.66), -int(r * 0.40)):
                draw.line([(cx - bw // 2, cy + dy), (cx + bw // 2, cy + dy)], fill=(226, 232, 240, 255), width=2)
        else:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(32, 40, 56, 255), outline=(148, 163, 184, 255), width=3)
            bar_w = int(r * 0.92)
            spacing = int(r * 0.42)
            for dy in (-spacing, 0, spacing):
                draw.rounded_rectangle(
                    [cx - bar_w // 2, cy + dy - 2, cx + bar_w // 2, cy + dy + 2],
                    radius=2,
                    fill=(248, 250, 252, 255)
                )

    elif key == "select":
        if fam == "playstation":
            pw = int(r * 1.15)
            ph = int(r * 1.62)
            draw.rounded_rectangle(
                [cx - pw // 2, cy - ph // 2 + 3, cx + pw // 2, cy + ph // 2 + 3],
                radius=pw // 2,
                fill=(32, 40, 56, 255),
                outline=(56, 189, 248, 255),
                width=3
            )
            top_y = cy - ph // 2 - 1
            draw.line([(cx, top_y), (cx, top_y - 6)], fill=(226, 232, 240, 255), width=3)
            draw.line([(cx - 5, top_y + 1), (cx - 9, top_y - 4)], fill=(226, 232, 240, 255), width=3)
            draw.line([(cx + 5, top_y + 1), (cx + 9, top_y - 4)], fill=(226, 232, 240, 255), width=3)
        else:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(32, 40, 56, 255), outline=(148, 163, 184, 255), width=3)
            sq = int(r * 0.62)
            off = int(r * 0.24)
            x1, y1 = cx - sq // 2 - off, cy - sq // 2 - off
            draw.rounded_rectangle([x1, y1, x1 + sq, y1 + sq], radius=3, outline=(203, 213, 225, 255), width=3)
            x2, y2 = cx - sq // 2 + off, cy - sq // 2 + off
            draw.rounded_rectangle([x2 - 2, y2 - 2, x2 + sq + 2, y2 + sq + 2], radius=3, fill=(32, 40, 56, 255))
            draw.rounded_rectangle([x2, y2, x2 + sq, y2 + sq], radius=3, outline=(248, 250, 252, 255), width=3)

    elif key in ("lb", "rb", "lt", "rt", "l1", "r1", "l2", "r2"):
        if fam == "playstation":
            ps_map = {"lb": "L1", "rb": "R1", "l1": "L1", "r1": "R1", "lt": "L2", "rt": "R2", "l2": "L2", "r2": "R2"}
            lbl = ps_map.get(key, key.upper())
        else:
            xb_map = {"l1": "LB", "r1": "RB", "l2": "LT", "r2": "RT"}
            lbl = xb_map.get(key, key.upper())
        bw = int(r * 2.1)
        bh = int(r * 1.45)
        draw.rounded_rectangle(
            [cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2],
            radius=int(bh * 0.42),
            fill=(30, 38, 54, 255),
            outline=(148, 163, 184, 255),
            width=3
        )
        draw.text((cx, cy - 1), lbl, font=font_bumper, fill=(248, 250, 252, 255), anchor="mm")


def render_button_icon_pil(btn_key: str, family: Optional[str] = None, size: int = 22) -> Image.Image:
    """
    Genera una imagen RGBA (supersampling 2x) de un botón individual del mando ('a', 'b', 'x', 'y', 'start', 'select', 'lb', 'rb', 'lt', 'rt')
    adaptada automáticamente al mando conectado (Xbox vs PlayStation).
    """
    if family is None:
        family = get_connected_controller_family()
    fam = "playstation" if family == "playstation" else "xbox"
    k = btn_key.lower()
    cache_key = (k, fam, size)
    if cache_key in _ICON_PIL_CACHE:
        return _ICON_PIL_CACHE[cache_key]

    scale = 2
    h2 = size * scale
    w2 = int(size * 1.25 * scale) if k in ("lb", "rb", "lt", "rt", "l1", "r1", "l2", "r2") else h2
    canvas = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    r = int(min(w2, h2) * 0.43)
    _draw_button_glyph(draw, k, fam, w2 // 2, h2 // 2, r)

    out_w = max(14, w2 // scale)
    downscaled = canvas.resize((out_w, size), Image.Resampling.LANCZOS)
    _ICON_PIL_CACHE[cache_key] = downscaled
    return downscaled


def get_button_icon_ctk(btn_key: str, family: Optional[str] = None, size: int = 20, scale: Optional[float] = None) -> ctk.CTkImage:
    """
    Devuelve un objeto CTkImage listo para incrustar en cualquier CTkButton o CTkLabel
    (ej: Cancelar con el circulito real (B) / (◯), Guardar con (Start), Aplicar con (A) / (✕), etc.).
    """
    from ui.display_scale import get_active_display_scale
    if family is None:
        family = get_connected_controller_family()
    fam = "playstation" if family == "playstation" else "xbox"
    k = btn_key.lower()
    sc = scale if scale is not None else get_active_display_scale()
    eff_size = max(14, int(round(size * sc)))
    cache_key = (k, fam, eff_size)
    cached = _ICON_CTK_CACHE.get(cache_key)
    if cached is not None:
        return cached
    pil_img = render_button_icon_pil(k, fam, size=eff_size)
    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(pil_img.width, pil_img.height))
    _ICON_CTK_CACHE[cache_key] = ctk_img
    return ctk_img


def render_controller_badge_pill(action: str, family: str = "xbox", height: int = 32) -> Image.Image:
    """Genera una píldora individual para una acción ('start', 'select', 'exit')."""
    family_norm = "playstation" if family == "playstation" else "xbox"
    scale = 2
    h2 = height * scale
    font_label = _load_font(int(h2 * 0.35), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)
    icon_r = int(h2 * 0.33)
    pad_x = int(h2 * 0.22)
    gap_txt = 10

    if action == "start":
        act_txt = "Vista"
        btn_k = "start"
    elif action == "select":
        act_txt = "Ocultar"
        btn_k = "select"
    else:
        act_txt = "Salir"
        btn_k = "y"

    aw = int(ddraw.textlength(act_txt, font=font_label))
    w2 = pad_x + (icon_r * 2) + gap_txt + aw + pad_x

    canvas = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([2, 2, w2 - 3, h2 - 3], radius=(h2 // 2) - 2, fill=(20, 24, 34, 255), outline=(48, 58, 80, 255), width=3)

    cy = h2 // 2
    _draw_button_glyph(draw, btn_k, family_norm, pad_x + icon_r, cy, icon_r)
    draw.text((pad_x + (icon_r * 2) + gap_txt, cy - 1), act_txt, font=font_label, fill=(248, 250, 252, 255), anchor="lm")

    target_w = max(20, w2 // scale)
    downscaled = canvas.resize((target_w, height), Image.Resampling.LANCZOS)
    r_ch, g_ch, b_ch, a_ch = downscaled.split()
    crisp_a = a_ch.point(lambda p: 255 if p >= 135 else 0)
    downscaled = Image.merge("RGBA", (r_ch, g_ch, b_ch, crisp_a))
    return prevent_transparency_color_collision(downscaled)


def render_controller_hud_strip(
    family: str = "xbox",
    height: int = 34,
    gap: int = 0
) -> Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]:
    """
    Compone una ÚNICA cápsula continua ultra-compacta con los 3 controles juntos:
      [ (☰) Vista  │  (⧉) Ocultar  │  (Y / △) Salir ]
    Elimina cualquier separación excesiva tanto en modo Big Picture como en modo Transparente.
    Devuelve (imagen_rgba, [(x1, y1, x2, y2, action_name), ...]).
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    key = (family_norm, height)
    if key in _STRIP_CACHE:
        return _STRIP_CACHE[key]

    scale = 2
    h2 = height * scale
    font_label = _load_font(int(h2 * 0.34), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)

    icon_r = int(h2 * 0.32)
    outer_pad = int(h2 * 0.28)
    item_gap = int(h2 * 0.24)
    icon_txt_gap = 9

    specs = [
        ("start", "start", "Vista"),
        ("select", "select", "Ocultar"),
        ("exit", "y", "Salir"),
    ]

    seg_widths = []
    for _, _, txt in specs:
        tw = int(ddraw.textlength(txt, font=font_label))
        seg_widths.append((icon_r * 2) + icon_txt_gap + tw)

    w2 = (outer_pad * 2) + sum(seg_widths) + (item_gap * 2 * (len(specs) - 1))
    canvas = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Cápsula única Liquid Glass continua
    draw.rounded_rectangle(
        [2, 2, w2 - 3, h2 - 3],
        radius=(h2 // 2) - 2,
        fill=(20, 23, 34, 255),
        outline=(43, 51, 69, 255),
        width=3
    )

    cy = h2 // 2
    cur_x = outer_pad
    boxes: List[Tuple[int, int, int, int, str]] = []

    for idx, ((act_name, btn_k, txt), seg_w) in enumerate(zip(specs, seg_widths)):
        seg_start = cur_x - (outer_pad if idx == 0 else item_gap)
        _draw_button_glyph(draw, btn_k, family_norm, cur_x + icon_r, cy, icon_r)
        tx = cur_x + (icon_r * 2) + icon_txt_gap
        draw.text((tx, cy - 1), txt, font=font_label, fill=(248, 250, 252, 255), anchor="lm")
        cur_x += seg_w
        seg_end = cur_x + (outer_pad if idx == len(specs) - 1 else item_gap)

        boxes.append((seg_start // scale, 0, seg_end // scale, height, act_name))

        if idx < len(specs) - 1:
            div_x = cur_x + item_gap
            draw.line([(div_x, int(h2 * 0.24)), (div_x, int(h2 * 0.76))], fill=(48, 58, 80, 255), width=2)
            cur_x += item_gap * 2

    target_w = max(40, w2 // scale)
    downscaled = canvas.resize((target_w, height), Image.Resampling.LANCZOS)

    r_ch, g_ch, b_ch, a_ch = downscaled.split()
    crisp_a = a_ch.point(lambda p: 255 if p >= 135 else 0)
    downscaled = Image.merge("RGBA", (r_ch, g_ch, b_ch, crisp_a))
    downscaled = prevent_transparency_color_collision(downscaled)

    _STRIP_CACHE[key] = (downscaled, boxes)
    return downscaled, boxes


_BP_TOP_HUD_CACHE: Dict[Tuple[str, str, Tuple[int, int, int], int], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}
_LAUNCH_PILL_CACHE: Dict[Tuple[str, bool, bool, int, int], Image.Image] = {}


def _draw_gear_icon(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    r: int,
    fg_col: Tuple[int, int, int, int] = (248, 250, 252, 255),
    bg_col: Tuple[int, int, int, int] = (20, 23, 34, 240)
):
    """Dibuja un engranaje vectorial nítido de 8 dientes (sin depender de fuentes Unicode que muestran cuadrados)."""
    num_teeth = 8
    r_outer = float(r)
    r_base = r * 0.72
    r_hole = max(3, int(r * 0.34))
    tooth_hw = max(2, int(r * 0.22))

    # Dientes del engranaje
    for i in range(num_teeth):
        ang = i * (2.0 * math.pi / num_teeth)
        ca, sa = math.cos(ang), math.sin(ang)
        pa, qa = -sa, ca
        x_in, y_in = cx + ca * (r_base * 0.75), cy + sa * (r_base * 0.75)
        x_out, y_out = cx + ca * r_outer, cy + sa * r_outer
        pts = [
            (x_in + pa * tooth_hw, y_in + qa * tooth_hw),
            (x_out + pa * (tooth_hw * 0.82), y_out + qa * (tooth_hw * 0.82)),
            (x_out - pa * (tooth_hw * 0.82), y_out - qa * (tooth_hw * 0.82)),
            (x_in - pa * tooth_hw, y_in - qa * tooth_hw),
        ]
        draw.polygon(pts, fill=fg_col)

    # Anillo principal y orificio central
    rb = int(round(r_base))
    draw.ellipse([cx - rb, cy - rb, cx + rb, cy + rb], fill=fg_col)
    draw.ellipse([cx - r_hole, cy - r_hole, cx + r_hole, cy + r_hole], fill=bg_col)


def _draw_battery_icon(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    h_ref: int,
    col: Tuple[int, int, int, int],
    pct_val: int = 75
):
    """Dibuja un icono vectorial nítido de batería horizontal con nivel de carga."""
    bw = int(h_ref * 0.52)
    bh = int(h_ref * 0.28)
    x0 = cx - bw // 2 - 2
    y0 = cy - bh // 2
    x1 = x0 + bw
    y1 = y0 + bh
    # Cuerpo de la batería
    draw.rounded_rectangle([x0, y0, x1, y1], radius=4, outline=col, width=3)
    # Borne positivo derecho
    cap_h = max(4, bh // 2)
    draw.rectangle([x1 + 1, cy - cap_h // 2, x1 + 4, cy + cap_h // 2], fill=col)
    # Relleno interior según nivel
    fill_Ratio = max(0.15, min(1.0, pct_val / 100.0))
    inner_max_w = max(2, (bw - 10))
    fill_w = max(2, int(round(inner_max_w * fill_Ratio)))
    draw.rectangle([x0 + 5, y0 + 5, x0 + 5 + fill_w, y1 - 5], fill=col)


def render_big_picture_top_hud(
    family: str = "xbox",
    battery_txt: str = "Mando",
    battery_col: Tuple[int, int, int] = (100, 116, 139),
    height: int = 36
) -> Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]:
    """
    Renderiza en RGBA con fondo 100% transparente todos los botones superiores derechos de Big Picture:
      [ ⚙ Opciones (X/□) ]   [ 🔋 -- ]   [ (☰) Vista │ (⧉) Ocultar │ (Y/△) Salir ]
    Permite que el wallpaper de fondo se extienda hasta arriba del todo (y=0) por detrás de los botones,
    eliminando por completo la barra gris superior y dibujando iconos vectoriales nítidos sin cuadrados Unicode.
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    if isinstance(battery_col, str):
        hc = battery_col.lstrip("#")
        if len(hc) == 6:
            try:
                battery_col = (int(hc[0:2], 16), int(hc[2:4], 16), int(hc[4:6], 16))
            except Exception:
                battery_col = (100, 116, 139)
        else:
            battery_col = (100, 116, 139)
    cache_key = (family_norm, battery_txt, battery_col, height)
    if cache_key in _BP_TOP_HUD_CACHE:
        return _BP_TOP_HUD_CACHE[cache_key]

    scale = 2
    h2 = height * scale
    font_lbl = _load_font(int(h2 * 0.34), bold=True)
    font_bat = _load_font(int(h2 * 0.33), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)
    cy = h2 // 2
    icon_r = int(h2 * 0.31)
    gear_r = int(h2 * 0.23)

    # 1. Píldora Menú: [ (⚙) Opciones (X/□) ]
    opt_txt = "Opciones"
    opt_tw = int(ddraw.textlength(opt_txt, font=font_lbl))
    pad_x = int(h2 * 0.34)
    gap_inner = int(h2 * 0.18)
    menu_w2 = pad_x + (gear_r * 2) + gap_inner + opt_tw + gap_inner + (icon_r * 2) + pad_x
    menu_img = Image.new("RGBA", (menu_w2, h2), (0, 0, 0, 0))
    mdraw = ImageDraw.Draw(menu_img)
    mdraw.rounded_rectangle(
        [2, 2, menu_w2 - 3, h2 - 3],
        radius=(h2 // 2) - 2,
        fill=(20, 23, 34, 240),
        outline=(43, 51, 69, 255),
        width=3
    )
    gx = pad_x + gear_r
    _draw_gear_icon(mdraw, gx, cy, gear_r, fg_col=(248, 250, 252, 255), bg_col=(20, 23, 34, 240))
    tx = gx + gear_r + gap_inner
    mdraw.text((tx, cy - 1), opt_txt, font=font_lbl, fill=(248, 250, 252, 255), anchor="lm")
    bx = tx + opt_tw + gap_inner + icon_r
    _draw_button_glyph(mdraw, "x", family_norm, bx, cy, icon_r)
    menu_down = menu_img.resize((menu_w2 // scale, height), Image.Resampling.LANCZOS)

    # 2. Píldora Batería: [ (🔋) 100% / Mando ] (limpiando emojis para evitar cuadrados Unicode)
    clean_bat = re.sub(r'[^\x20-\x7E\xA0-\xFF%]', '', battery_txt or "").strip() or "Mando"
    pct_match = re.search(r'(\d+)\s*%', clean_bat)
    pct_num = int(pct_match.group(1)) if pct_match else (75 if "Alta" in clean_bat or "Media" in clean_bat else 45)
    bat_tw = int(ddraw.textlength(clean_bat, font=font_bat))
    bat_icon_w = int(h2 * 0.62)
    bat_w2 = pad_x + bat_icon_w + gap_inner + bat_tw + pad_x
    bat_img = Image.new("RGBA", (bat_w2, h2), (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(bat_img)
    bdraw.rounded_rectangle(
        [2, 2, bat_w2 - 3, h2 - 3],
        radius=(h2 // 2) - 2,
        fill=(20, 23, 34, 240),
        outline=(43, 51, 69, 255),
        width=3
    )
    bat_rgba = (*battery_col, 255)
    _draw_battery_icon(bdraw, pad_x + bat_icon_w // 2, cy, h2, bat_rgba, pct_val=pct_num)
    bdraw.text((pad_x + bat_icon_w + gap_inner, cy - 1), clean_bat, font=font_bat, fill=bat_rgba, anchor="lm")
    bat_down = bat_img.resize((bat_w2 // scale, height), Image.Resampling.LANCZOS)

    # 3. Cápsula unificada: [ (☰) Vista │ (⧉) Ocultar │ (Y/△) Salir ]
    strip_down, strip_boxes = render_controller_hud_strip(family_norm, height=height)

    pill_gap = 6
    tot_w = menu_down.width + pill_gap + bat_down.width + pill_gap + strip_down.width
    combined = Image.new("RGBA", (tot_w, height), (0, 0, 0, 0))

    x_cursor = 0
    boxes: List[Tuple[int, int, int, int, str]] = []

    combined.paste(menu_down, (x_cursor, 0), menu_down)
    boxes.append((x_cursor, 0, x_cursor + menu_down.width, height, "menu"))
    x_cursor += menu_down.width + pill_gap

    combined.paste(bat_down, (x_cursor, 0), bat_down)
    boxes.append((x_cursor, 0, x_cursor + bat_down.width, height, "battery"))
    x_cursor += bat_down.width + pill_gap

    combined.paste(strip_down, (x_cursor, 0), strip_down)
    for (bx1, by1, bx2, by2, act) in strip_boxes:
        boxes.append((x_cursor + bx1, by1, x_cursor + bx2, by2, act))

    res = (combined, boxes)
    if len(_BP_TOP_HUD_CACHE) > 24:
        _BP_TOP_HUD_CACHE.clear()
    _BP_TOP_HUD_CACHE[cache_key] = res
    return res


def render_launch_button_pill(
    family: str = "xbox",
    hovered: bool = False,
    disabled: bool = False,
    width: int = 248,
    height: int = 48
) -> Image.Image:
    """
    Renderiza la píldora inferior '▶ INICIAR JUEGO (A/✕)' en RGBA con esquinas suaves transparentes
    y triángulo Play vectorial nítido (sin cuadrados Unicode).
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    key = (family_norm, bool(hovered), bool(disabled), width, height)
    if key in _LAUNCH_PILL_CACHE:
        return _LAUNCH_PILL_CACHE[key]

    scale = 2
    w2 = width * scale
    h2 = height * scale
    canvas = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    if disabled:
        fill_col = (30, 38, 54, 210)
        border_col = (55, 65, 85, 220)
        txt_col = (148, 163, 184, 230)
    elif hovered:
        fill_col = (0, 98, 204, 255)
        border_col = (96, 165, 250, 255)
        txt_col = (255, 255, 255, 255)
    else:
        fill_col = (0, 122, 255, 255)
        border_col = (56, 148, 255, 255)
        txt_col = (255, 255, 255, 255)

    draw.rounded_rectangle(
        [2, 2, w2 - 3, h2 - 3],
        radius=(h2 // 2) - 2,
        fill=fill_col,
        outline=border_col,
        width=3
    )

    font_btn = _load_font(int(h2 * 0.29), bold=True)
    txt = "INICIAR JUEGO"
    tw = int(draw.textlength(txt, font=font_btn))
    play_w = int(h2 * 0.22)
    icon_r = int(h2 * 0.24)
    gap = 14
    total_content = play_w + 12 + tw + gap + (icon_r * 2)
    start_x = (w2 - total_content) // 2
    cy = h2 // 2

    # Triángulo Play vectorial nítido
    py_half = int(h2 * 0.13)
    draw.polygon(
        [(start_x, cy - py_half), (start_x, cy + py_half), (start_x + play_w, cy)],
        fill=txt_col
    )
    txt_x = start_x + play_w + 12
    draw.text((txt_x, cy - 1), txt, font=font_btn, fill=txt_col, anchor="lm")
    _draw_button_glyph(draw, "a", family_norm, txt_x + tw + gap + icon_r, cy, icon_r)

    downscaled = canvas.resize((width, height), Image.Resampling.LANCZOS)
    _LAUNCH_PILL_CACHE[key] = downscaled
    return downscaled


_FILTER_CAPSULE_CACHE: Dict[Tuple[str, int, str, int, int, int], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}

def render_filter_capsule(
    filter_label: str,
    count: int,
    family: str = "xbox",
    height: int = 36,
    shelf_index: int = 0,
    total_shelves: int = 1
) -> Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]:
    """
    Renderiza la píldora superior izquierda de Estantería / Carrusel en RGBA estilo Glassmorphism:
      Si hay > 1 estantería: [ (▲) ‹  FAVORITOS (4) • 1/3  › (▼) ]
      Si hay 1 estantería:   [  TODOS LOS JUEGOS (42)  ]
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    clean_lbl = (
        filter_label
        .replace("⭐", "★")
        .replace("🎮", "")
        .replace("⏳", "")
        .replace("🔥", "")
        .replace("🏆", "")
        .replace("🕹️", "")
        .replace("🏷️", "")
        .replace("💤", "")
        .strip()
    )
    cache_key = (clean_lbl, count, family_norm, height, shelf_index, total_shelves)
    if cache_key in _FILTER_CAPSULE_CACHE:
        return _FILTER_CAPSULE_CACHE[cache_key]

    scale = 2
    h2 = height * scale
    cy = h2 // 2
    font_lbl = _load_font(int(h2 * 0.32), bold=True)
    font_arr = _load_font(int(h2 * 0.36), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)

    has_multi = (total_shelves > 1)
    if has_multi:
        disp_text = f"{clean_lbl.upper()} ({count})  ·  {shelf_index + 1}/{total_shelves}"
    else:
        disp_text = f"{clean_lbl.upper()} ({count})"

    tw = int(ddraw.textlength(disp_text, font=font_lbl))
    arr_w = int(ddraw.textlength("▲", font=font_arr)) if has_multi else 0

    icon_r = int(h2 * 0.28)
    pad_x = int(h2 * 0.32)
    gap = int(h2 * 0.20)

    if has_multi:
        tot_w2 = pad_x + arr_w + gap + tw + gap + arr_w + pad_x
    else:
        tot_w2 = pad_x + tw + pad_x

    canvas = Image.new("RGBA", (tot_w2, h2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Cápsula de cristal translúcida
    draw.rounded_rectangle(
        [2, 2, tot_w2 - 3, h2 - 3],
        radius=(h2 // 2) - 2,
        fill=(20, 23, 34, 240),
        outline=(43, 51, 69, 255),
        width=3
    )

    if has_multi:
        # 1. Flecha arriba ▲
        arr1_x = pad_x + (arr_w // 2)
        draw.text((arr1_x, cy - 1), "▲", font=font_arr, fill=(56, 189, 248, 255), anchor="mm")

        # 2. Texto central
        tx = pad_x + arr_w + gap + (tw // 2)
        txt_col = (56, 189, 248, 255) if "★" in clean_lbl or "FAVORITOS" in clean_lbl else (248, 250, 252, 255)
        draw.text((tx, cy - 1), disp_text, font=font_lbl, fill=txt_col, anchor="mm")

        # 3. Flecha abajo ▼
        arr2_x = tx + (tw // 2) + gap + (arr_w // 2)
        draw.text((arr2_x, cy - 1), "▼", font=font_arr, fill=(56, 189, 248, 255), anchor="mm")

        downscaled = canvas.resize((tot_w2 // scale, height), Image.Resampling.LANCZOS)
        w_final = tot_w2 // scale

        left_bound = (pad_x + arr_w + gap // 2) // scale
        right_bound = (tot_w2 - pad_x - arr_w - gap // 2) // scale
        boxes = [
            (0, 0, left_bound, height, "shelf_prev"),
            (left_bound, 0, right_bound, height, "filter_menu"),
            (right_bound, 0, w_final, height, "shelf_next"),
        ]
    else:
        tx = pad_x + (tw // 2)
        txt_col = (248, 250, 252, 255)
        draw.text((tx, cy - 1), disp_text, font=font_lbl, fill=txt_col, anchor="mm")

        downscaled = canvas.resize((tot_w2 // scale, height), Image.Resampling.LANCZOS)
        w_final = tot_w2 // scale
        boxes = [
            (0, 0, w_final, height, "filter_menu")
        ]

    res = (downscaled, boxes)
    if len(_FILTER_CAPSULE_CACHE) > 32:
        _FILTER_CAPSULE_CACHE.clear()
    _FILTER_CAPSULE_CACHE[cache_key] = res
    return res

