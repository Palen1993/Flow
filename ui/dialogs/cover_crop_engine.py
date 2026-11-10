"""
Motor de renderizado Pillow para la cuadrícula virtual (120 FPS) y previsualización en vivo
(Carátulas 1:1 Jewel Case y Escenario Wallpaper 16:9 Big Picture) de CoverPickerDialog.
"""
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw

from core.coverflow_engine import (
    create_jewel_case,
    prepare_flat_cover,
    create_procedural_album,
    adapt_wallpaper_to_widescreen,
    compose_big_picture_wallpaper_bg,
)


def prepare_card_and_preview_images(
    im: Image.Image,
    is_wp: bool,
    card_w: int
) -> Tuple[Image.Image, Image.Image, Tuple[int, int]]:
    """Pre-escala la miniatura de tarjeta y la imagen de vista previa en el hilo secundario (0 carga en el hilo UI)."""
    iw, ih = im.size
    orig_size = (iw, ih)

    # 1. Imagen ligera para la vista previa en vivo (máx 600px de lado mayor para respuesta en <2ms)
    max_prev = 600.0
    if max(iw, ih) > max_prev:
        sc_p = max_prev / float(max(iw, ih))
        pw, ph = max(1, int(iw * sc_p)), max(1, int(ih * sc_p))
        preview_im = im.convert("RGBA").resize((pw, ph), Image.Resampling.BILINEAR)
    else:
        preview_im = im.convert("RGBA")

    # 2. Miniatura exacta lista para pegar con .paste() directo sobre la tarjeta
    if is_wp:
        max_tw = max(130, card_w - 22)
        max_th = 114
        th_h = int(max_tw * 9 / 16)
        if th_h > max_th:
            th_h = max_th
            max_tw = int(max_th * 16 / 9)
        card_thumb = adapt_wallpaper_to_widescreen(preview_im, width=max_tw, height=th_h)
    else:
        if iw > ih * 1.18:
            max_tw = max(140, card_w - 24)
            scale = min(float(max_tw) / max(1, iw), 124.0 / max(1, ih))
        else:
            scale = min(132.0 / max(1, iw), 132.0 / max(1, ih))
        tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
        card_thumb = preview_im.convert("RGB").resize((tw, th), Image.Resampling.BILINEAR)

    return preview_im, card_thumb, orig_size


def draw_grid_card_on_master(
    img: Image.Image,
    item: Dict[str, Any],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    is_sel: bool,
    is_wp: bool,
    card_thumb: Optional[Image.Image],
    pil_im: Optional[Image.Image],
    font_title: Any,
    font_badge: Any,
    font_btn: Any,
) -> None:
    """Dibuja o actualiza instantáneamente (< 0.1ms) una única tarjeta sobre el lienzo maestro."""
    draw = ImageDraw.Draw(img)

    # Limpiar área de la tarjeta antes de redibujarla
    draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], fill=(15, 18, 24))

    bg_col = (28, 48, 82) if is_sel else (20, 23, 34)
    border_col = (0, 229, 255) if is_sel else (36, 44, 61)
    border_w = 3 if is_sel else 1

    draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=bg_col, outline=border_col, width=border_w)

    cx = (x0 + x1) // 2
    if card_thumb is not None:
        tw, th = card_thumb.size
        tx = cx - tw // 2
        ty = (y0 + 14 + (118 - th) // 2) if is_wp else (y0 + 10 + (132 - th) // 2)
        img.paste(card_thumb, (tx, ty))
        outline_c = ((56, 189, 248) if is_sel else (55, 65, 85)) if is_wp else (55, 65, 85)
        draw.rectangle([tx - 1, ty - 1, tx + tw, ty + th], outline=outline_c, width=1)
    else:
        box_hw = 76 if is_wp else 55
        draw.rounded_rectangle([cx - box_hw, y0 + 18, cx + box_hw, y0 + 132], radius=8, fill=(13, 15, 22), outline=(32, 38, 52))
        draw.text((cx, y0 + 75), "Cargando...", fill=(100, 116, 139), anchor="mm", font=font_badge)

    title_str = item.get("name", "Juego")
    if len(title_str) > 25:
        title_str = title_str[:23] + "…"
    draw.text((cx, y0 + 156), title_str, fill=(248, 250, 252), anchor="mm", font=font_title)

    src = item.get("source", "Web")
    if pil_im is not None:
        iw, ih = item.get("orig_size", pil_im.size)
        if is_wp:
            if ih < 1080 or iw < 1920:
                iw, ih = 1920, 1080
                item["orig_size"] = (1920, 1080)

            if ih >= 2160 or iw >= 3840:
                b_txt = f"✦ 4K UHD ({iw}×{ih})"
            elif ih >= 1440 or iw >= 2560:
                b_txt = f"✦ 2K QHD ({iw}×{ih})"
            else:
                b_txt = f"✦ 1080p Full HD ({iw}×{ih})"
            b_col = (56, 189, 248)
        else:
            adiff = abs(iw - ih) / float(max(1, max(iw, ih)))
            if adiff <= 0.14:
                b_txt = f"✦ 1:1 Cuadrada ({iw}×{ih})"
                b_col = (52, 199, 89)
            elif iw > ih * 1.2:
                b_txt = f"✦ HD 16:9 ({iw}×{ih})"
                b_col = (56, 189, 248)
            else:
                b_txt = f"{src} ({iw}×{ih})"
                b_col = (56, 189, 248)
    else:
        if is_wp:
            b_txt = "✦ 1080p Full HD"
            b_col = (56, 189, 248)
        else:
            b_txt = f"✦ {src}" if item.get("is_square") else src
            b_col = (52, 199, 89) if item.get("is_square") else (148, 163, 184)

    draw.text((cx, y0 + 178), b_txt, fill=b_col, anchor="mm", font=font_badge)

    btn_y0 = y0 + 196
    btn_y1 = y0 + 224
    btn_fill = (0, 122, 255) if is_sel else (31, 37, 51)
    btn_txt = "✓ Seleccionado" if (is_sel and is_wp) else ("✓ Seleccionada" if is_sel else "Ver en Previa")
    btn_tcol = (255, 255, 255) if is_sel else (203, 213, 225)
    draw.rounded_rectangle(
        [x0 + 14, btn_y0, x1 - 14, btn_y1],
        radius=10,
        fill=btn_fill,
        outline=(255, 255, 255) if is_sel else None,
        width=2 if is_sel else 0
    )
    draw.text((cx, (btn_y0 + btn_y1) // 2), btn_txt, fill=btn_tcol, anchor="mm", font=font_btn)


def compose_cover_preview_stage(
    base_im: Image.Image,
    game_name: str,
    fit_mode: str,
    crop_anchor: str,
    crop_offset: Optional[float],
    box_size: int = 186,
) -> Image.Image:
    """Genera el lienzo RGBA (240x248) con el estuche Jewel Case 3D y reflejo inferior."""
    jewel = create_jewel_case(
        base_im,
        name=game_name,
        size=box_size,
        fit_mode=fit_mode,
        crop_anchor=crop_anchor,
        crop_offset=crop_offset,
    )
    flat_with_refl, _, _ = prepare_flat_cover(jewel, box_size, has_reflection=True)
    stage = Image.new("RGBA", (240, 248), (11, 13, 19, 255))
    ox = (240 - box_size) // 2
    oy = 6
    stage.paste(flat_with_refl, (ox, oy), flat_with_refl)
    return stage
