import math
import re
import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from core.coverflow_engine import prevent_transparency_color_collision
from gamepad_manager import get_connected_controller_family

_ICON_PIL_CACHE: Dict[Tuple[str, str, int], Image.Image] = {}
_ICON_CTK_CACHE: Dict[Tuple[str, str, int], ctk.CTkImage] = {}
_ICON_CTK_TK_APP: Optional[Any] = None
_STRIP_CACHE: Dict[Tuple[str, int, str], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}


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
    global _ICON_CTK_TK_APP
    from ui.display_scale import get_active_display_scale
    if family is None:
        family = get_connected_controller_family()
    fam = "playstation" if family == "playstation" else "xbox"
    k = btn_key.lower()
    sc = scale if scale is not None else get_active_display_scale()
    eff_size = max(14, int(round(size * sc)))

    current_tk = getattr(tk._default_root, "tk", None)
    if current_tk is None:
        _ICON_CTK_CACHE.clear()
        _ICON_CTK_TK_APP = None
        pil_img = render_button_icon_pil(k, fam, size=eff_size)
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(pil_img.width, pil_img.height))

    if current_tk is not _ICON_CTK_TK_APP:
        _ICON_CTK_CACHE.clear()
        _ICON_CTK_TK_APP = current_tk

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


def _lerp_rgba(
    c1: Tuple[int, int, int, int],
    c2: Tuple[int, int, int, int],
    t: float
) -> Tuple[int, int, int, int]:
    return (
        int(round(c1[0] + (c2[0] - c1[0]) * t)),
        int(round(c1[1] + (c2[1] - c1[1]) * t)),
        int(round(c1[2] + (c2[2] - c1[2]) * t)),
        int(round(c1[3] + (c2[3] - c1[3]) * t)),
    )


def _draw_apple_glass_pill(
    canvas: Image.Image,
    box: Tuple[int, int, int, int],
    radius: int,
    hovered: bool = False,
    primary: bool = False,
    disabled: bool = False,
    solid_mode: bool = False,
) -> None:
    """Pinta una píldora estilo Apple Dark Glassmorphism sobre lienzo 2x RGBA."""
    w2, h2 = canvas.size
    x0, y0, x1, y1 = box
    bw = max(4, x1 - x0 + 1)
    bh = max(4, y1 - y0 + 1)

    if solid_mode:
        # Modo Mini (ColorKey Win32): gradiente sutil con alpha binario sólido sin halo externo
        top_c = (72, 76, 96, 255) if hovered else (40, 42, 58, 255)
        bot_c = (46, 48, 64, 255) if hovered else (20, 22, 32, 255)
        border_c = (212, 222, 244, 255) if hovered else (112, 118, 144, 255)
        border_w = 3 if hovered else 2
        glow_c = None
    elif primary and disabled:
        top_c = (38, 40, 54, 195)
        bot_c = (22, 24, 34, 205)
        border_c = (78, 82, 100, 185)
        border_w = 2
        glow_c = None
    elif primary and hovered:
        top_c = (86, 184, 255, 255)
        bot_c = (12, 130, 250, 255)
        border_c = (204, 236, 255, 245)
        border_w = 3
        glow_c = (45, 160, 255, 140)
    elif primary:
        top_c = (30, 148, 255, 255)
        bot_c = (0, 100, 230, 255)
        border_c = (140, 204, 255, 135)
        border_w = 2
        glow_c = (0, 122, 255, 100)
    elif hovered:
        top_c = (94, 100, 124, 192)
        bot_c = (50, 54, 70, 202)
        border_c = (232, 238, 255, 220)
        border_w = 3
        glow_c = (205, 222, 255, 58)
    else:
        top_c = (52, 54, 70, 162)
        bot_c = (18, 19, 29, 172)
        border_c = (255, 255, 255, 62)
        border_w = 2
        glow_c = (0, 0, 0, 74)

    # Sombra / halo exterior suave manteniendo esquinas exteriores en alpha=0
    if glow_c is not None and not solid_mode:
        shadow = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        shift_y = 0 if (primary or hovered) else 2
        sdraw.rounded_rectangle(
            [x0, y0 + shift_y, x1, min(h2 - 1, y1 + shift_y)],
            radius=radius,
            fill=glow_c,
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=3 if (primary or hovered) else 2))
        canvas.alpha_composite(shadow)

    # Gradiente vertical translúcido del vidrio
    grad_col = Image.new("RGBA", (1, bh))
    grad_col.putdata([_lerp_rgba(top_c, bot_c, y / max(1, bh - 1)) for y in range(bh)])
    grad_box = grad_col.resize((bw, bh), Image.Resampling.BILINEAR)

    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, bw - 1, bh - 1], radius=radius, fill=255)

    pill_body = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    pill_body.paste(grad_box, (x0, y0), mask)

    # Reflejo especular sutil superior + borde 1px
    pdraw = ImageDraw.Draw(pill_body)
    if not solid_mode and not disabled:
        spec_col = (255, 255, 255, 118 if hovered else 76)
        spec_pad = max(6, radius // 2)
        if bw > spec_pad * 2:
            pdraw.line([(x0 + spec_pad, y0 + 2), (x1 - spec_pad, y0 + 2)], fill=spec_col, width=2)
    pdraw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=border_c, width=border_w)
    canvas.alpha_composite(pill_body)


def _draw_chevron_down(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    size: int,
    col: Tuple[int, int, int, int],
    width: int = 3
) -> None:
    """Dibuja un chevron vectorizado hacia abajo '⌄' limpio."""
    hw = max(3, int(round(size * 0.52)))
    hh = max(2, int(round(size * 0.28)))
    draw.line([(cx - hw, cy - hh), (cx, cy + hh), (cx + hw, cy - hh)], fill=col, width=width, joint="curve")


def render_controller_hud_strip(
    family: str = "xbox",
    height: int = 34,
    gap: int = 0,
    hovered_action: Optional[str] = None,
    solid_mode: bool = True
) -> Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]:
    """
    Compone una ÚNICA cápsula continua ultra-compacta con los 3 controles juntos:
      [ (☰) Vista  │  (⧉) Ocultar  │  (Y / △) Salir ]
    Elimina cualquier separación excesiva tanto en modo Big Picture como en modo Transparente.
    Devuelve (imagen_rgba, [(x1, y1, x2, y2, action_name), ...]).
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    hov_norm = hovered_action if hovered_action in ("start", "select", "exit") else ""
    key = (family_norm, height, f"{hov_norm}|{'S' if solid_mode else 'G'}")
    if key in _STRIP_CACHE:
        return _STRIP_CACHE[key]

    scale = 2
    h2 = height * scale
    font_label = _load_font(int(h2 * 0.34), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)

    icon_r = int(h2 * 0.31)
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

    # Cápsula única Apple Dark Glass continua
    pad = 2 if solid_mode else 4
    box_rad = max(8, ((h2 - (pad * 2)) // 2))
    _draw_apple_glass_pill(
        canvas,
        box=(pad, pad, w2 - 1 - pad, h2 - 1 - pad),
        radius=box_rad,
        hovered=False,
        solid_mode=solid_mode,
    )
    draw = ImageDraw.Draw(canvas)

    cy = h2 // 2
    cur_x = outer_pad
    boxes: List[Tuple[int, int, int, int, str]] = []

    for idx, ((act_name, btn_k, txt), seg_w) in enumerate(zip(specs, seg_widths)):
        seg_start = cur_x - (outer_pad if idx == 0 else item_gap)
        seg_end = cur_x + seg_w + (outer_pad if idx == len(specs) - 1 else item_gap)

        if act_name == hov_norm and not solid_mode:
            hl_pad_y = pad + 4
            hl_x0 = max(pad + 4, seg_start + 3)
            hl_x1 = min(w2 - 1 - pad - 4, seg_end - 3)
            hl_rad = max(6, (h2 - (hl_pad_y * 2)) // 2)
            draw.rounded_rectangle(
                [hl_x0, hl_pad_y, hl_x1, h2 - 1 - hl_pad_y],
                radius=hl_rad,
                fill=(255, 255, 255, 44),
                outline=(232, 238, 255, 190),
                width=2
            )

        _draw_button_glyph(draw, btn_k, family_norm, cur_x + icon_r, cy, icon_r)
        tx = cur_x + (icon_r * 2) + icon_txt_gap
        draw.text((tx, cy - 1), txt, font=font_label, fill=(255, 255, 255, 255), anchor="lm")
        cur_x += seg_w

        boxes.append((seg_start // scale, 0, seg_end // scale, height, act_name))

        if idx < len(specs) - 1:
            div_x = cur_x + item_gap
            draw.line([(div_x, int(h2 * 0.24)), (div_x, int(h2 * 0.76))], fill=(255, 255, 255, 48 if not solid_mode else 110), width=2)
            cur_x += item_gap * 2

    target_w = max(40, w2 // scale)
    downscaled = canvas.resize((target_w, height), Image.Resampling.LANCZOS)

    if solid_mode:
        r_ch, g_ch, b_ch, a_ch = downscaled.split()
        crisp_a = a_ch.point(lambda p: 255 if p >= 135 else 0)
        downscaled = Image.merge("RGBA", (r_ch, g_ch, b_ch, crisp_a))
    downscaled = prevent_transparency_color_collision(downscaled)

    if len(_STRIP_CACHE) > 24:
        _STRIP_CACHE.clear()
    _STRIP_CACHE[key] = (downscaled, boxes)
    return downscaled, boxes


_BP_TOP_HUD_CACHE: Dict[Tuple[str, str, Tuple[int, int, int], int, str], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}
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
    height: int = 36,
    hovered_action: Optional[str] = None
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
    hov_norm = hovered_action if hovered_action in ("menu", "battery", "start", "select", "exit") else ""
    cache_key = (family_norm, battery_txt, battery_col, height, hov_norm)
    if cache_key in _BP_TOP_HUD_CACHE:
        return _BP_TOP_HUD_CACHE[cache_key]

    scale = 2
    h2 = height * scale
    font_lbl = _load_font(int(h2 * 0.34), bold=True)
    font_bat = _load_font(int(h2 * 0.33), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)
    cy = h2 // 2
    icon_r = int(h2 * 0.30)
    gear_r = int(h2 * 0.22)

    pad = 4
    pill_rad = max(8, ((h2 - (pad * 2)) // 2))

    # 1. Píldora Menú: [ (⚙) Opciones (X/□) ]
    opt_txt = "Opciones"
    opt_tw = int(ddraw.textlength(opt_txt, font=font_lbl))
    pad_x = int(h2 * 0.34)
    gap_inner = int(h2 * 0.18)
    menu_w2 = pad_x + (gear_r * 2) + gap_inner + opt_tw + gap_inner + (icon_r * 2) + pad_x
    menu_img = Image.new("RGBA", (menu_w2, h2), (0, 0, 0, 0))
    _draw_apple_glass_pill(
        menu_img,
        box=(pad, pad, menu_w2 - 1 - pad, h2 - 1 - pad),
        radius=pill_rad,
        hovered=(hov_norm == "menu"),
    )
    mdraw = ImageDraw.Draw(menu_img)
    gx = pad_x + gear_r
    gear_hole_col = (72, 76, 96, 225) if hov_norm == "menu" else (34, 36, 50, 220)
    _draw_gear_icon(mdraw, gx, cy, gear_r, fg_col=(255, 255, 255, 255), bg_col=gear_hole_col)
    tx = gx + gear_r + gap_inner
    mdraw.text((tx, cy - 1), opt_txt, font=font_lbl, fill=(255, 255, 255, 255), anchor="lm")
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
    _draw_apple_glass_pill(
        bat_img,
        box=(pad, pad, bat_w2 - 1 - pad, h2 - 1 - pad),
        radius=pill_rad,
        hovered=(hov_norm == "battery"),
    )
    bdraw = ImageDraw.Draw(bat_img)
    bat_rgba = (*battery_col, 255)
    _draw_battery_icon(bdraw, pad_x + bat_icon_w // 2, cy, h2, bat_rgba, pct_val=pct_num)
    bdraw.text((pad_x + bat_icon_w + gap_inner, cy - 1), clean_bat, font=font_bat, fill=bat_rgba, anchor="lm")
    bat_down = bat_img.resize((bat_w2 // scale, height), Image.Resampling.LANCZOS)

    # 3. Cápsula unificada: [ (☰) Vista │ (⧉) Ocultar │ (Y/△) Salir ]
    strip_down, strip_boxes = render_controller_hud_strip(
        family_norm,
        height=height,
        hovered_action=hov_norm if hov_norm in ("start", "select", "exit") else None,
        solid_mode=False,
    )

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

    combined = prevent_transparency_color_collision(combined)
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

    pad = 5
    pill_rad = max(10, ((h2 - (pad * 2)) // 2))
    _draw_apple_glass_pill(
        canvas,
        box=(pad, pad, w2 - 1 - pad, h2 - 1 - pad),
        radius=pill_rad,
        hovered=bool(hovered),
        primary=True,
        disabled=bool(disabled),
    )
    draw = ImageDraw.Draw(canvas)
    txt_col = (158, 158, 176, 230) if disabled else (255, 255, 255, 255)

    font_btn = _load_font(int(h2 * 0.28), bold=True)
    txt = "INICIAR JUEGO"
    tw = int(draw.textlength(txt, font=font_btn))
    play_w = int(h2 * 0.21)
    icon_r = int(h2 * 0.23)
    gap = 14
    total_content = play_w + 12 + tw + gap + (icon_r * 2)
    start_x = (w2 - total_content) // 2
    cy = h2 // 2

    # Triángulo Play vectorial nítido
    py_half = int(h2 * 0.12)
    draw.polygon(
        [(start_x, cy - py_half), (start_x, cy + py_half), (start_x + play_w, cy)],
        fill=txt_col
    )
    txt_x = start_x + play_w + 12
    draw.text((txt_x, cy - 1), txt, font=font_btn, fill=txt_col, anchor="lm")
    _draw_button_glyph(draw, "a", family_norm, txt_x + tw + gap + icon_r, cy, icon_r)

    downscaled = prevent_transparency_color_collision(canvas.resize((width, height), Image.Resampling.LANCZOS))
    if len(_LAUNCH_PILL_CACHE) > 24:
        _LAUNCH_PILL_CACHE.clear()
    _LAUNCH_PILL_CACHE[key] = downscaled
    return downscaled


def clean_pillow_text(text: str, mode: str = "filter") -> str:
    """Limpia emojis fuera de rango bitmap antes de renderizar texto en Pillow (evita glifos '□')."""
    raw = str(text or "")
    if mode == "status":
        cleaned = (
            raw
            .replace("🖥", "")
            .replace("⏱", "Tiempo:")
            .replace("🎮", "")
            .replace("⚙", "Opciones")
            .replace("\ufe0f", "")
            .strip()
        )
        while "  •" in cleaned:
            cleaned = cleaned.replace("  •", " •")
        return cleaned.replace(" • ", "   •   ")
    return (
        raw
        .replace("⭐", "★")
        .replace("🎮", "")
        .replace("⏳", "")
        .replace("🔥", "")
        .replace("🏆", "")
        .replace("🕹️", "")
        .replace("🏷️", "")
        .replace("💤", "")
        .replace("\ufe0f", "")
        .strip()
    )


_FILTER_CAPSULE_CACHE: Dict[Tuple[str, int, str, int, int, int, bool, str], Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]] = {}

def render_filter_capsule(
    filter_label: str,
    count: int,
    family: str = "xbox",
    height: int = 36,
    shelf_index: int = 0,
    total_shelves: int = 1,
    transparent_key_safe: bool = False,
    hovered_action: Optional[str] = None,
) -> Tuple[Image.Image, List[Tuple[int, int, int, int, str]]]:
    """
    Renderiza la píldora superior izquierda de Estantería / Carrusel en RGBA estilo Glassmorphism:
      Si hay > 1 estantería: [ ▲  │  ▼ FAVORITOS (4) · 1/3  ⌄  │  ▼ ]
      Si hay 1 estantería:   [ ▼  TODOS LOS JUEGOS (42)  ⌄ ]
    """
    family_norm = "playstation" if family == "playstation" else "xbox"
    t_safe = bool(transparent_key_safe)
    hov_norm = hovered_action if hovered_action in ("shelf_prev", "filter_menu", "shelf_next") else ""
    clean_lbl = clean_pillow_text(filter_label, mode="filter")
    cache_key = (clean_lbl, count, family_norm, height, shelf_index, total_shelves, t_safe, hov_norm)
    if cache_key in _FILTER_CAPSULE_CACHE:
        return _FILTER_CAPSULE_CACHE[cache_key]

    scale = 2
    h2 = height * scale
    cy = h2 // 2
    font_lbl = _load_font(int(h2 * 0.31), bold=True)
    font_arr = _load_font(int(h2 * 0.34), bold=True)

    dummy = Image.new("RGBA", (10, 10))
    ddraw = ImageDraw.Draw(dummy)

    has_multi = (total_shelves > 1)
    if has_multi:
        disp_text = f"{clean_lbl.upper()} ({count})  ·  {shelf_index + 1}/{total_shelves}"
    else:
        disp_text = f"{clean_lbl.upper()} ({count})"

    tw = int(ddraw.textlength(disp_text, font=font_lbl))
    arr_w = int(ddraw.textlength("▲", font=font_arr)) if has_multi else 0

    pad_x = int(h2 * 0.30)
    gap = int(h2 * 0.18)
    tri_hw = max(5, int(h2 * 0.10))
    tri_hh = max(4, int(h2 * 0.08))
    gap_inner = int(h2 * 0.14)
    chev_s = max(6, int(h2 * 0.16))
    chev_w = int(chev_s * 1.4)
    center_w = (tri_hw * 2) + gap_inner + tw + gap_inner + chev_w

    if has_multi:
        tot_w2 = pad_x + arr_w + gap + center_w + gap + arr_w + pad_x
    else:
        tot_w2 = pad_x + center_w + pad_x

    canvas = Image.new("RGBA", (tot_w2, h2), (0, 0, 0, 0))

    pad = 2 if t_safe else 4
    pill_rad = max(8, ((h2 - (pad * 2)) // 2))
    _draw_apple_glass_pill(
        canvas,
        box=(pad, pad, tot_w2 - 1 - pad, h2 - 1 - pad),
        radius=pill_rad,
        hovered=(hov_norm == "filter_menu"),
        solid_mode=t_safe,
    )
    draw = ImageDraw.Draw(canvas)

    def _draw_center_block(start_x: int):
        tcx = start_x + tri_hw
        tri_col = (232, 236, 248, 255)
        draw.polygon(
            [(tcx - tri_hw, cy - tri_hh), (tcx + tri_hw, cy - tri_hh), (tcx, cy + tri_hh)],
            fill=tri_col
        )
        tx = start_x + (tri_hw * 2) + gap_inner
        draw.text((tx, cy - 1), disp_text, font=font_lbl, fill=(255, 255, 255, 255), anchor="lm")
        ccx = tx + tw + gap_inner + (chev_w // 2)
        _draw_chevron_down(draw, ccx, cy, chev_s, col=(226, 230, 242, 245), width=3)

    if has_multi:
        left_bound_px = pad_x + arr_w + (gap // 2)
        right_bound_px = tot_w2 - pad_x - arr_w - (gap // 2)
        hl_pad_y = pad + 4
        hl_rad = max(6, (h2 - (hl_pad_y * 2)) // 2)
        if hov_norm == "shelf_prev" and not t_safe:
            draw.rounded_rectangle(
                [pad + 4, hl_pad_y, left_bound_px, h2 - 1 - hl_pad_y],
                radius=hl_rad,
                fill=(255, 255, 255, 44),
                outline=(232, 238, 255, 190),
                width=2
            )
        elif hov_norm == "shelf_next" and not t_safe:
            draw.rounded_rectangle(
                [right_bound_px, hl_pad_y, tot_w2 - 1 - pad - 4, h2 - 1 - hl_pad_y],
                radius=hl_rad,
                fill=(255, 255, 255, 44),
                outline=(232, 238, 255, 190),
                width=2
            )

        # 1. Flecha arriba ▲
        arr1_x = pad_x + (arr_w // 2)
        arr1_col = (255, 255, 255, 255) if hov_norm == "shelf_prev" else (210, 214, 230, 255)
        draw.text((arr1_x, cy - 1), "▲", font=font_arr, fill=arr1_col, anchor="mm")

        # 2. Bloque central: ▼ ETIQUETA (N) · i/n ⌄
        _draw_center_block(pad_x + arr_w + gap)

        # 3. Flecha abajo ▼
        arr2_x = tot_w2 - pad_x - (arr_w // 2)
        arr2_col = (255, 255, 255, 255) if hov_norm == "shelf_next" else (210, 214, 230, 255)
        draw.text((arr2_x, cy - 1), "▼", font=font_arr, fill=arr2_col, anchor="mm")

        downscaled = canvas.resize((tot_w2 // scale, height), Image.Resampling.LANCZOS)
        w_final = tot_w2 // scale

        left_bound = left_bound_px // scale
        right_bound = right_bound_px // scale
        boxes = [
            (0, 0, left_bound, height, "shelf_prev"),
            (left_bound, 0, right_bound, height, "filter_menu"),
            (right_bound, 0, w_final, height, "shelf_next"),
        ]
    else:
        _draw_center_block(pad_x)
        downscaled = canvas.resize((tot_w2 // scale, height), Image.Resampling.LANCZOS)
        w_final = tot_w2 // scale
        boxes = [
            (0, 0, w_final, height, "filter_menu")
        ]

    if t_safe:
        r_ch, g_ch, b_ch, a_ch = downscaled.split()
        crisp_a = a_ch.point(lambda p: 255 if p >= 135 else 0)
        downscaled = Image.merge("RGBA", (r_ch, g_ch, b_ch, crisp_a))
    downscaled = prevent_transparency_color_collision(downscaled)

    res = (downscaled, boxes)
    if len(_FILTER_CAPSULE_CACHE) > 48:
        _FILTER_CAPSULE_CACHE.clear()
    _FILTER_CAPSULE_CACHE[cache_key] = res
    return res

