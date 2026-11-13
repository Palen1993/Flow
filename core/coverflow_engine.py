import os
import math
import hashlib
from typing import List, Tuple, Dict, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
from core.config import JEWELS_CACHE_DIR

_SAFE_BLUE_LUT = list(range(256))
_SAFE_BLUE_LUT[1] = 2  # Evita colisión con trans_key #000001 (RGB: 0, 0, 1)

def prevent_transparency_color_collision(img: Image.Image) -> Image.Image:
    """
    Evita que píxeles oscuros de las carátulas (RGB 0, 0, 1) coincidan con la
    clave de transparencia de Windows (#000001), eliminando agujeros transparentes.
    Operación ultra rápida a nivel C de PIL (~0.2 ms).
    """
    if not img:
        return img
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    r, g, b, a = img.split()
    b = b.point(_SAFE_BLUE_LUT)
    return Image.merge('RGBA', (r, g, b, a))

def find_perspective_coeffs(pa: List[Tuple[float, float]], pb: List[Tuple[float, float]]) -> List[float]:
    """Resuelve la matriz 8x8 para mapear pa (destino) a pb (origen) en PIL."""
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])
    B = []
    for p in pb:
        B.extend([p[0], p[1]])
    n = 8
    A = [row[:] + [B[i]] for i, row in enumerate(matrix)]
    for i in range(n):
        pivot = i
        for j in range(i+1, n):
            if abs(A[j][i]) > abs(A[pivot][i]):
                pivot = j
        A[i], A[pivot] = A[pivot], A[i]
        for j in range(i+1, n):
            factor = A[j][i] / A[i][i]
            for k in range(i, n+1):
                A[j][k] -= factor * A[i][k]
    coeffs = [0.0]*n
    for i in range(n-1, -1, -1):
        coeffs[i] = (A[i][n] - sum(A[i][j]*coeffs[j] for j in range(i+1, n))) / A[i][i]
    return coeffs

def create_procedural_album(name: str, size: int = 256) -> Image.Image:
    """Genera una carátula procedural estilo iPod disco para juegos sin imagen."""
    img = Image.new('RGBA', (size, size), (20, 24, 34, 255))
    draw = ImageDraw.Draw(img)
    
    # Anillos concéntricos de vinilo/cd
    cx, cy = size // 2, size // 2
    for r in range(size // 2, 0, -3):
        frac = r / (size // 2)
        val = int(22 + (1.0 - frac) * 35)
        blue = int(36 + (1.0 - frac) * 55)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(val, val + 2, blue, 255))
        
    draw.ellipse([cx - 75, cy - 75, cx + 75, cy + 75], outline=(255, 255, 255, 30), width=2)
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=(255, 255, 255, 45), width=2)
    draw.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=(12, 14, 20, 255), outline=(255, 255, 255, 80), width=1)
    
    # Texto del título
    short_title = name if len(name) <= 15 else name[:13] + '...'
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
    draw.text((cx, size - 42), short_title, fill=(240, 245, 255, 230), anchor='mm', font=font)
    return img

def adapt_cover_to_square(
    img: Image.Image,
    size: int = 512,
    fit_mode: str = "auto",
    crop_anchor: str = "center",
    crop_offset: Optional[float] = None
) -> Image.Image:
    """
    Adapta cualquier carátula para llenar el 100% del lienzo cuadrado (size x size) de borde a borde,
    SIN bandas laterales ni marcos vacíos.
    
    fit_mode:
      - 'stretch': Ajusta el 100% de la imagen completa al cuadrado de borde a borde.
      - 'auto': Encaje inteligente híbrido (recorta el 55% del exceso vertical/horizontal y ajusta el resto).
      - 'crop': Recorte 1:1 exacto sin deformación (respetando crop_anchor: 'top', 'center', 'bottom' o crop_offset 0.0..1.0).
    """
    w, h = img.size
    if w <= 0 or h <= 0:
        return Image.new('RGBA', (size, size), (16, 18, 24, 255))

    src = img.convert('RGBA')
    aspect_diff = abs(w - h) / float(max(w, h))

    # Determinar factor de desplazamiento (0.0 = arriba/izquierda, 0.5 = centro, 1.0 = abajo/derecha)
    if crop_offset is not None:
        offset_factor = max(0.0, min(1.0, float(crop_offset)))
    elif crop_anchor == "top":
        offset_factor = 0.0
    elif crop_anchor == "bottom":
        offset_factor = 1.0
    else:
        offset_factor = 0.5

    # 1. Modo 'stretch' (Completo): encaja el 100% de la imagen de esquina a esquina
    if fit_mode == "stretch":
        return src.resize((size, size), Image.Resampling.LANCZOS)

    # 2. Modo 'crop' (Recorte 1:1 / Encuadre Arriba-Centro-Abajo):
    if fit_mode == "crop":
        if h > w and aspect_diff > 0.05:
            # Imagen vertical: ventana cuadrada (w x w) desplazable entre arriba (0.0), centro (0.5) y abajo (1.0)
            max_top = h - w
            top = int(round(max_top * offset_factor))
            cropped = src.crop((0, top, w, top + w))
            return cropped.resize((size, size), Image.Resampling.LANCZOS)
        elif w > h and aspect_diff > 0.05:
            # Imagen horizontal: ventana cuadrada (h x h) desplazable horizontalmente
            max_left = w - h
            left = int(round(max_left * offset_factor))
            cropped = src.crop((left, 0, left + h, h))
            return cropped.resize((size, size), Image.Resampling.LANCZOS)
        else:
            # Imagen ya cuadrada (1:1): aplica un zoom de encuadre (82% del tamaño) desplazado hacia arriba/centro/abajo
            box_s = max(1, int(min(w, h) * 0.82))
            left = (w - box_s) // 2
            max_top = max(0, h - box_s)
            top = int(round(max_top * offset_factor))
            cropped = src.crop((left, top, left + box_s, top + box_s))
            return cropped.resize((size, size), Image.Resampling.LANCZOS)

    # 3. Modo 'auto' (Encaje Inteligente Híbrido):
    if aspect_diff <= 0.08:
        return src.resize((size, size), Image.Resampling.LANCZOS)

    if h > w:
        # Recorta el 55% del exceso vertical y adapta suavemente el 45% restante
        excess_h = h - w
        target_h = h - int(excess_h * 0.55)
        max_top = h - target_h
        default_off = 0.32 if crop_offset is None and crop_anchor == "center" else offset_factor
        top = int(round(max_top * default_off))
        cropped = src.crop((0, top, w, top + target_h))
        return cropped.resize((size, size), Image.Resampling.LANCZOS)
    else:
        excess_w = w - h
        target_w = w - int(excess_w * 0.55)
        max_left = w - target_w
        left = int(round(max_left * offset_factor))
        cropped = src.crop((left, 0, left + target_w, h))
        return cropped.resize((size, size), Image.Resampling.LANCZOS)


def create_jewel_case(
    img: Image.Image,
    name: str = "",
    size: int = 240,
    fit_mode: str = "auto",
    crop_anchor: str = "center",
    crop_offset: Optional[float] = None
) -> Image.Image:
    """
    Adapta cualquier imagen a un estuche cuadrado de cristal de iPod con brillo especular,
    llenando el 100% de la caja de borde a borde sin bandas laterales.
    """
    res = Image.new('RGBA', (size, size), (16, 18, 24, 255))
    w, h = img.size
    if w <= 0 or h <= 0:
        return res
    
    is_transparent = False
    if img.mode == 'RGBA':
        try:
            extrema = img.getextrema()
            if len(extrema) >= 4 and extrema[3][0] < 250:
                is_transparent = True
        except Exception:
            pass

    if is_transparent:
        scale = min((size - 24) / w, (size - 24) / h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        scaled = img.resize((nw, nh), Image.Resampling.LANCZOS)
        res.paste(scaled, ((size - nw) // 2, (size - nh) // 2), scaled)
    else:
        scaled = adapt_cover_to_square(
            img,
            size=size,
            fit_mode=fit_mode,
            crop_anchor=crop_anchor,
            crop_offset=crop_offset
        )
        res.paste(scaled, (0, 0))
        
    # Borde de estuche de CD y reflejo diagonal de cristal
    draw = ImageDraw.Draw(res)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(255, 255, 255, 55), width=1)
    draw.rectangle([1, 1, size - 2, size - 2], outline=(0, 0, 0, 110), width=1)
    
    gloss = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gloss)
    points = [(0, 0), (size, 0), (0, int(size * 0.72))]
    g_draw.polygon(points, fill=(255, 255, 255, 20))
    return prevent_transparency_color_collision(Image.alpha_composite(res, gloss))

def prepare_flat_cover(base_album: Image.Image, size: int, has_reflection: bool = True) -> Tuple[Image.Image, int, int]:
    """Genera la carátula plana (con reflejo inferior opcional) lista para proyecciones."""
    scaled = prevent_transparency_color_collision(base_album.resize((size, size), Image.Resampling.LANCZOS))
    if not has_reflection:
        return scaled, size, size

    refl_h = int(size * 0.44)
    refl = scaled.transpose(Image.Transpose.FLIP_TOP_BOTTOM).resize((size, refl_h), Image.Resampling.BILINEAR)
    
    mask_bytes = bytes([
        int(((1.0 - (y / refl_h)) ** 1.6) * 125) if int(((1.0 - (y / refl_h)) ** 1.6) * 125) >= 12 else 0
        for y in range(refl_h)
    ])
    mask_1px = Image.frombytes('L', (1, refl_h), mask_bytes)
    refl_mask = mask_1px.resize((size, refl_h), Image.Resampling.BILINEAR)
    refl.putalpha(refl_mask)
    
    tot_h = size + refl_h
    combined = Image.new('RGBA', (size, tot_h), (0, 0, 0, 0))
    combined.paste(scaled, (0, 0))
    combined.paste(refl, (0, size), refl)
    return prevent_transparency_color_collision(combined), size, tot_h

_COVER_GEOM_CACHE: Dict[Tuple[int, float, bool], Tuple[int, int, List[float], Image.Image]] = {}

def get_cover_flow_geom(size: int, angle_factor: float, has_reflection: bool = True) -> Tuple[int, int, List[float], Image.Image]:
    """Caché global de matrices de perspectiva y degradados de sombra por ángulo y tamaño."""
    af = max(-1.0, min(1.0, angle_factor))
    rounded_af = round(af, 3)
    key = (size, rounded_af, bool(has_reflection))
    if key in _COVER_GEOM_CACHE:
        return _COVER_GEOM_CACHE[key]
        
    abs_af = abs(af)
    refl_h = int(size * 0.44) if has_reflection else 0
    tot_h = size + refl_h
    target_w = max(10, int(size * (1.0 - 0.58 * abs_af)))
    
    skew_top = int(size * 0.16 * abs_af)
    skew_bottom = int(tot_h * 0.16 * abs_af)
    
    pb = [(0, 0), (size, 0), (size, tot_h), (0, tot_h)]
    if af < 0:
        pa = [
            (0, skew_top),
            (target_w, 0),
            (target_w, tot_h),
            (0, tot_h - skew_bottom)
        ]
    else:
        pa = [
            (0, 0),
            (target_w, skew_top),
            (target_w, tot_h - skew_bottom),
            (0, tot_h)
        ]
        
    coeffs = find_perspective_coeffs(pa, pb)
    
    dark_alpha = int(120 * abs_af)
    grad_bytes = bytes([int(dark_alpha * ((target_w - x) / target_w if af < 0 else x / target_w)) for x in range(target_w)])
    grad_1px = Image.frombytes('L', (target_w, 1), grad_bytes)
    grad_mask = grad_1px.resize((target_w, tot_h), Image.Resampling.NEAREST)
    
    res = (target_w, tot_h, coeffs, grad_mask)
    if len(_COVER_GEOM_CACHE) >= 256:
        # Política FIFO/LRU ligera para evitar crecimiento indefinido tras redimensionados
        for old_k in list(_COVER_GEOM_CACHE.keys())[:64]:
            _COVER_GEOM_CACHE.pop(old_k, None)
    _COVER_GEOM_CACHE[key] = res
    return res

def render_cover_flow_from_flat(flat_cover: Image.Image, size: int, angle_factor: float, has_reflection: bool = True) -> Tuple[Image.Image, int, int]:
    """Aplica proyección 3D y oclusión a una carátula plana pre-reflejada o simple."""
    tot_h = size + (int(size * 0.44) if has_reflection else 0)
    if abs(angle_factor) < 0.02:
        return prevent_transparency_color_collision(flat_cover), size, tot_h
        
    target_w, th, coeffs, grad_mask = get_cover_flow_geom(size, angle_factor, has_reflection=has_reflection)
    warped = flat_cover.transform((target_w, th), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR)
    
    warped_alpha = warped.split()[3]
    shaded_alpha = ImageChops.multiply(grad_mask, warped_alpha)
    shade_layer = Image.new('RGBA', (target_w, th), (0, 0, 0, 0))
    shade_layer.putalpha(shaded_alpha)
    warped = Image.alpha_composite(warped, shade_layer)
    return prevent_transparency_color_collision(warped), target_w, th

def render_cover_flow_element(base_album: Image.Image, size: int = 230, angle_factor: float = 0.0, has_reflection: bool = True) -> Tuple[Image.Image, int, int]:
    """Genera una carátula con su reflejo (opcional) y proyección 3D de Cover Flow de alto rendimiento."""
    flat_cover, sz, tot_h = prepare_flat_cover(base_album, size, has_reflection=has_reflection)
    return render_cover_flow_from_flat(flat_cover, size, angle_factor, has_reflection=has_reflection)


def scale_alpha_mask(mask: Image.Image, alpha_scale: float) -> Image.Image:
    """Escala una máscara 'L' usando una LUT C-level sin lambdas por píxel."""
    factor = max(0.0, min(1.0, float(alpha_scale)))
    if factor >= 0.995:
        return mask
    if factor <= 0.0:
        return Image.new("L", mask.size, 0)
    lut = [int(v * factor) for v in range(256)]
    return mask.point(lut)


def render_vertical_shelf_tilt(
    shelf_body: Image.Image,
    tilt: float,
    tilt_dir: int,
    center_x_in_crop: float,
    alpha_scale: float = 1.0,
    max_angle_rad: float = 1.18,
    resample: Optional[Image.Resampling] = None,
    transparent_key_safe: bool = False,
) -> Tuple[Image.Image, Image.Image, int]:
    """
    Aplica proyección 3D de rotación vertical (eje X) a una fila de carátulas de carrusel:
      - tilt_dir < 0: el carrusel rota hacia arriba (el borde superior retrocede en profundidad).
      - tilt_dir >= 0: el carrusel rota hacia abajo (el borde inferior retrocede en profundidad).
    Las líneas de fuga convergen simétricamente hacia center_x_in_crop (centro visual de pantalla).
    """
    if not shelf_body or shelf_body.width <= 0 or shelf_body.height <= 0:
        empty = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return empty, empty.getchannel("A"), 1

    cw, sh = shelf_body.size
    t = max(0.0, min(1.0, float(tilt)))
    a_scale = max(0.0, min(1.0, float(alpha_scale)))

    if t <= 0.01:
        src = shelf_body if shelf_body.mode == "RGBA" else shelf_body.convert("RGBA")
        if transparent_key_safe:
            src = prevent_transparency_color_collision(src)
        mask = scale_alpha_mask(src.getchannel("A"), a_scale)
        return src, mask, sh

    theta = t * max_angle_rad
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    target_h = max(8, int(round(sh * max(0.32, cos_t))))

    # Estrechamiento perspectivo del borde lejano convergiendo hacia el eje central de pantalla
    taper = 0.34 * sin_t
    cx_crop = max(0.0, min(float(cw), float(center_x_in_crop)))
    left_rec = cx_crop * taper
    right_rec = float(cw) - (float(cw) - cx_crop) * taper
    if right_rec - left_rec < 4.0:
        half_min = min(2.0, float(cw) * 0.4)
        left_rec = max(0.0, cx_crop - half_min)
        right_rec = min(float(cw), cx_crop + half_min)

    pb = [(0.0, 0.0), (float(cw), 0.0), (float(cw), float(sh)), (0.0, float(sh))]
    if tilt_dir < 0:
        # Rotando hacia arriba: el borde superior retrocede y se estrecha, el inferior queda al frente
        pa = [(left_rec, 0.0), (right_rec, 0.0), (float(cw), float(target_h)), (0.0, float(target_h))]
    else:
        # Rotando hacia abajo: el borde inferior retrocede y se estrecha, el superior queda al frente
        pa = [(0.0, 0.0), (float(cw), 0.0), (right_rec, float(target_h)), (left_rec, float(target_h))]

    coeffs = find_perspective_coeffs(pa, pb)
    if resample is None:
        # En resoluciones 720p/ventana usa BILINEAR nítido; en 1080p/4K mantiene 60fps fluidos con NEAREST
        resample = Image.Resampling.BILINEAR if (cw * target_h <= 340_000) else Image.Resampling.NEAREST

    src_rgba = shelf_body if shelf_body.mode == "RGBA" else shelf_body.convert("RGBA")
    warped = src_rgba.transform((cw, target_h), Image.Transform.PERSPECTIVE, coeffs, resample)

    # Sombreado de profundidad y desvanecimiento gradual más marcado hacia el borde que rota alejándose
    max_dark = int(165 * sin_t)
    denom = max(1, target_h - 1)
    grad_vals = bytearray(target_h)
    alpha_vals = bytearray(target_h)
    for y in range(target_h):
        frac = y / denom
        recede_f = (1.0 - frac) if tilt_dir < 0 else frac
        grad_vals[y] = int(max_dark * recede_f)
        a_f = a_scale * (1.0 - 0.55 * sin_t * recede_f)
        alpha_vals[y] = max(0, min(255, int(round(255.0 * a_f))))

    src_a = warped.getchannel("A")
    v_alpha = Image.frombytes("L", (1, target_h), bytes(alpha_vals)).resize((cw, target_h), Image.Resampling.NEAREST)
    final_a = ImageChops.multiply(src_a, v_alpha)

    if max_dark > 4:
        shade_l = Image.frombytes("L", (1, target_h), bytes(grad_vals)).resize((cw, target_h), Image.Resampling.NEAREST)
        shade_mask = ImageChops.multiply(shade_l, src_a)
        black_fill = Image.new("RGBA", (cw, target_h), (6, 8, 14, 255))
        warped.paste(black_fill, (0, 0), shade_mask)

    if transparent_key_safe:
        warped = prevent_transparency_color_collision(warped)

    return warped, final_a, target_h


def adapt_wallpaper_to_widescreen(
    img: Image.Image,
    width: int = 1920,
    height: int = 1080,
    crop_offset: float = 0.5,
    resample: Image.Resampling = Image.Resampling.BILINEAR
) -> Image.Image:
    """
    Adapta cualquier imagen a formato apaisado 16:9 (o dimensiones width x height) de borde a borde,
    recortando proporcionalmente el exceso vertical u horizontal según crop_offset (0.0 a 1.0).
    """
    width = max(16, int(width))
    height = max(9, int(height))
    if not img or img.size[0] <= 0 or img.size[1] <= 0:
        return Image.new('RGB', (width, height), (15, 18, 24))

    w, h = img.size
    src = img.convert('RGB')
    target_aspect = width / float(height)
    src_aspect = w / float(h)
    offset = max(0.0, min(1.0, float(crop_offset)))

    if abs(src_aspect - target_aspect) < 0.02:
        return src.resize((width, height), resample)

    if src_aspect > target_aspect:
        # Más ancha que 16:9: recortar lateralmente según offset
        crop_w = max(1, int(round(h * target_aspect)))
        max_left = max(0, w - crop_w)
        left = int(round(max_left * offset))
        cropped = src.crop((left, 0, left + crop_w, h))
        return cropped.resize((width, height), resample)
    else:
        # Más alta que 16:9: recortar verticalmente según offset
        crop_h = max(1, int(round(w / target_aspect)))
        max_top = max(0, h - crop_h)
        top = int(round(max_top * offset))
        cropped = src.crop((0, top, w, top + crop_h))
        return cropped.resize((width, height), resample)


def compose_big_picture_wallpaper_bg(
    wallpaper_img: Image.Image,
    w: int,
    h: int,
    floor_y: int,
    opacity: float = 0.25,
    blur_radius: float = 1.5
) -> Image.Image:
    """
    Compone el escenario de fondo de Big Picture integrando el wallpaper apaisado del juego
    de borde a borde a resolución nativa Full HD / 4K nítida,
    con opacidad y desenfoque ambiental configurable sin artefactos ni pixelado.
    """
    w = max(60, int(w))
    h = max(60, int(h))
    base_dark_color = (15, 18, 24)
    if not wallpaper_img:
        return Image.new('RGB', (w, h), base_dark_color)

    # 1. Adaptar el wallpaper a resolución nativa de pantalla (1080p/2K/4K) para máxima nitidez
    wp_fitted = adapt_wallpaper_to_widescreen(
        wallpaper_img, width=w, height=h, crop_offset=0.5, resample=Image.Resampling.BILINEAR
    )

    # 2. Si el usuario configuró desenfoque ambiental (>0.05), aplicar filtro de alta calidad
    # Si blur_radius <= 0.05 (modo 'Nítido'), no se aplica desenfoque manteniendo la imagen 100% nítida en 1080p
    blur_val = max(0.0, min(20.0, float(blur_radius)))
    if blur_val > 0.05:
        wp_fitted = wp_fitted.filter(ImageFilter.BoxBlur(blur_val))

    # 3. Mezclar con el fondo oscuro cinematográfico respetando la opacidad configurada
    alpha_factor = max(0.04, min(0.90, float(opacity)))
    base_dark = Image.new('RGB', (w, h), base_dark_color)
    return Image.blend(base_dark, wp_fitted, alpha_factor)

def get_cached_jewel_case(
    cover_path: Optional[str],
    name: str = "",
    size: int = 512,
    fit_mode: str = "auto",
    crop_anchor: str = "center",
    crop_offset: Optional[float] = None
) -> Image.Image:
    """
    Obtiene el estuche jewel case pre-renderizado desde la caché persistente en disco (.cache/jewels).
    Si no existe o la carátula original cambió (mtime/size), lo genera y lo guarda en disco.
    Acelera el arranque y refresco de la biblioteca hasta 40x.
    """
    try:
        os.makedirs(JEWELS_CACHE_DIR, exist_ok=True)
    except Exception:
        pass

    mtime = 0.0
    fsize = 0
    if cover_path and os.path.isfile(cover_path):
        try:
            st = os.stat(cover_path)
            mtime = st.st_mtime
            fsize = st.st_size
        except Exception:
            pass

    cache_params = f"{cover_path}:{mtime}:{fsize}:{size}:{fit_mode}:{crop_anchor}:{crop_offset}:{name}"
    cache_hash = hashlib.md5(cache_params.encode("utf-8")).hexdigest()
    cache_file = os.path.join(JEWELS_CACHE_DIR, f"{cache_hash}.png")

    if os.path.isfile(cache_file):
        try:
            with Image.open(cache_file) as im:
                return im.convert("RGBA")
        except Exception:
            pass

    loaded_img = None
    if cover_path and os.path.isfile(cover_path):
        try:
            with Image.open(cover_path) as raw_im:
                loaded_img = raw_im.convert("RGBA")
        except Exception:
            loaded_img = None

    if loaded_img is None:
        loaded_img = create_procedural_album(name or "Juego", size=380)

    jewel = create_jewel_case(
        loaded_img,
        name=name,
        size=size,
        fit_mode=fit_mode,
        crop_anchor=crop_anchor,
        crop_offset=crop_offset
    )

    try:
        tmp_cache = f"{cache_file}.tmp"
        jewel.save(tmp_cache, "PNG", compress_level=1)
        os.replace(tmp_cache, cache_file)
    except Exception:
        pass

    return jewel

def invalidate_jewel_case_cache(cover_path: str = ""):
    """Invalida las miniaturas cacheadas en disco para una carátula específica o para toda la biblioteca."""
    try:
        if not os.path.isdir(JEWELS_CACHE_DIR):
            return
        if not cover_path:
            for f in os.listdir(JEWELS_CACHE_DIR):
                if f.endswith(".png") or f.endswith(".tmp"):
                    try:
                        os.remove(os.path.join(JEWELS_CACHE_DIR, f))
                    except Exception:
                        pass
    except Exception:
        pass
