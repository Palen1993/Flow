import os
import sys
import re
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor

from core.scanner import clean_game_name
from core.config import COVERS_DIR, WALLPAPERS_DIR

STEAM_INFINITE_URL = "https://store.steampowered.com/search/results/"
GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"
}

IMAGE_REQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.google.com/"
}

_CANDIDATES_CACHE: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

MAX_IMAGE_DOWNLOAD_BYTES = 15 * 1024 * 1024  # 15 MB máximo de seguridad

_SEARCH_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "onto", "upon", "about", "of", "in", "to", "on", "at", "by",
    "del", "las", "los", "una", "uno", "por", "para", "con", "sin", "sobre", "el", "la", "de", "en", "y",
    "game", "games", "video", "videogame", "pc", "windows", "edition", "deluxe", "standard",
    "ultimate", "collector", "collectors", "collection", "remastered", "remake",
    "resynced", "definitive", "complete", "goty", "year", "version", "repack",
    "pack", "dlc", "bundle", "anthology", "trilogy", "saga", "series", "episode",
    "part", "chapter", "vol", "volume", "official", "cover", "boxart", "wallpaper",
    "wallpapers", "background", "backgrounds", "1920x1080", "1080p", "4k", "hd", "uhd",
    "images", "image", "photo", "photos", "free", "top", "buy", "online", "shop", "review"
}

_UMBRELLA_BRAND_WORDS = {
    "lego", "marvel", "marvels", "disney", "tom", "clancy", "clancys",
    "sid", "meier", "meiers", "clive", "barker", "barkers"
}

_COMMON_GENERIC_TITLE_WORDS = {
    "dark", "black", "knight", "legacy", "world", "king", "new", "modern",
    "origins", "chronicles", "legends", "shadow", "shadows", "war", "wars",
    "age", "solid", "creed", "assassins", "assassin", "metal", "gear",
    "call", "duty", "final", "fantasy", "resident", "evil", "grand", "theft", "auto",
    "star", "super", "bros", "story", "journey", "next", "door", "revival"
}

_SPAM_URL_OR_TITLE_SUBSTRINGS = (
    "lego.com/cdn/cs/set",
    "bbystatic.com",
    "jaysbrickblog.com",
    "brickabrac",
    "brickset.com",
    "bricklink.com",
    "rebrickable.com",
    "creator 3-in-1",
    "creative brick box",
    "building toy set",
    "building set",
    "minifigures series",
    "lego classic",
    "lego friends",
    "lego technic",
    "lego city neuheiten",
)


def _extract_meaningful_tokens(text: str) -> List[str]:
    """Extrae palabras clave significativas en minúsculas ignorando stopwords y años sueltos."""
    if not text:
        return []
    normalized = text.lower()
    normalized = re.sub(r"[’'`´™®©]", "", normalized)
    raw_words = re.findall(r"[a-z0-9]{2,}", normalized)
    tokens: List[str] = []
    for w in raw_words:
        if w in _SEARCH_STOPWORDS:
            continue
        if re.fullmatch(r"20[12]\d", w):
            continue
        if w == "assassin":
            w = "assassins"
        if w not in tokens:
            tokens.append(w)
    return tokens


def _is_candidate_relevant(title: str, url: str, desc: str, query: str) -> bool:
    """
    Verifica estrictamente que un resultado (de Steam, GOG, SteamGridDB o Web)
    pertenezca explícitamente al juego buscado y no a juguetes genéricos, listas ni otros juegos.
    """
    q_tokens = _extract_meaningful_tokens(query)
    if not q_tokens:
        return True

    unquoted_url = urllib.parse.unquote(url or "")
    combined_raw = f"{title or ''} {unquoted_url}".lower()
    for spam_sub in _SPAM_URL_OR_TITLE_SUBSTRINGS:
        if spam_sub in combined_raw or spam_sub in (desc or "").lower():
            return False

    cand_tokens = set(_extract_meaningful_tokens(combined_raw))
    if not cand_tokens:
        return False

    # 1. Si el juego tiene una marca paraguas (ej. 'lego'), DEBE estar en el título o URL del candidato
    for brand in _UMBRELLA_BRAND_WORDS:
        if brand in q_tokens and brand not in cand_tokens:
            return False

    # 2. Juego de 1 sola palabra significativa (ej. 'Viewfinder', 'Hellraiser')
    if len(q_tokens) == 1:
        return q_tokens[0] in cand_tokens

    # 3. Juego de 2 palabras significativas (ej. 'Split Fiction') -> exigir ambas palabras
    if len(q_tokens) == 2:
        return all(t in cand_tokens for t in q_tokens)

    # 4. Juego de 3 o más palabras significativas:
    non_brand = [t for t in q_tokens if t not in _UMBRELLA_BRAND_WORDS]
    distinctive = [t for t in non_brand if t not in _COMMON_GENERIC_TITLE_WORDS]
    if not distinctive:
        distinctive = non_brand or q_tokens

    # Si hay 1 o 2 palabras distintivas específicas (ej. ['batman'], ['harry', 'potter'], ['snake', 'eater'], ['flag']),
    # exigir que TODAS ellas estén presentes en el título o URL del candidato
    if len(distinctive) <= 2:
        if not all(d in cand_tokens for d in distinctive):
            return False
    else:
        if sum(1 for d in distinctive if d in cand_tokens) < 2:
            return False

    # Si empieza por marca + franquicia (ej. 'lego batman ...' o 'lego harry potter'), exigir la palabra inmediatamente posterior a la marca
    if q_tokens[0] in _UMBRELLA_BRAND_WORDS and len(q_tokens) >= 2:
        primary_subject = q_tokens[1]
        if primary_subject not in cand_tokens:
            return False

    matched_count = sum(1 for t in q_tokens if t in cand_tokens)
    min_required = 2 if len(q_tokens) <= 4 else 3
    if q_tokens[0] in _UMBRELLA_BRAND_WORDS and q_tokens[0] in cand_tokens and q_tokens[1] in cand_tokens:
        min_required = 2

    return matched_count >= min_required

def _safe_read_response(resp, max_bytes: int = MAX_IMAGE_DOWNLOAD_BYTES, chunk_size: int = 64 * 1024) -> bytes:
    """Lee el cuerpo de la respuesta en streaming limitando el tamaño máximo contra bombas de descompresión."""
    data = bytearray()
    while True:
        chunk = resp.read(chunk_size)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise ValueError(f"La imagen excede el límite de tamaño seguro ({max_bytes // (1024 * 1024)} MB)")
    return bytes(data)

def search_google_web_covers(raw_query: str, max_results: int = 18) -> List[Dict[str, Any]]:
    """
    Busca carátulas y key art de alta resolución en una petición ultrarrápida (~400ms)
    filtrando estrictamente que pertenezcan explícitamente al juego buscado.
    """
    if not raw_query or not raw_query.strip():
        return []

    query = raw_query.strip()
    clean_q = re.sub(r'[\(\)\[\]\{\}]', '', query).strip()
    q_enc = urllib.parse.quote(f"{clean_q} game cover key art")
    # +filterui:imagesize-large evita que Bing inyecte carruseles de compras/juguetes genéricos y fuerza imágenes HD
    url = f"https://www.bing.com/images/search?q={q_enc}&qft=+filterui:imagesize-large&form=HDRSC2&first=1"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    seen_urls = set()
    results: List[Dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=1.8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            matches = re.findall(r'class="iusc"[^>]*m="([^"]+)"', html)
            for m in matches:
                raw_json = m.replace('&quot;', '"').replace('&amp;', '&')
                try:
                    data = json.loads(raw_json)
                    murl = data.get("murl")
                    turl = data.get("turl")
                    title = data.get("t", clean_q)
                    desc = data.get("desc", "")
                    if not murl or murl in seen_urls:
                        continue
                    if not _is_candidate_relevant(title, murl, desc, clean_q):
                        continue
                    lower_m = murl.lower()
                    if any(ext in lower_m for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "image" in lower_m or "upload" in lower_m or "cover" in lower_m or "box" in lower_m:
                        seen_urls.add(murl)
                        src_label = "SteamGridDB" if "steamgriddb" in lower_m else "Carátula / Key Art HD"
                        results.append({
                            "id": f"web_{len(results)}",
                            "name": title,
                            "poster_url": murl,
                            "thumb_url": turl or murl,
                            "is_square": "512x512" in lower_m or "1024x1024" in lower_m,
                            "is_vertical": True,
                            "source": src_label,
                            "desc": desc
                        })
                        if len(results) >= max_results:
                            break
                except Exception:
                    pass
    except Exception:
        pass

    return results


def search_steamgriddb_covers(raw_query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """
    Busca carátulas verticales y cuadradas en SteamGridDB:
      - Si existe STEAMGRIDDB_API_KEY en el entorno, usa la API REST v2 oficial.
      - En modo 0-config (sin API key), extrae directamente grids del CDN de SteamGridDB verificando relevancia.
    """
    if not raw_query or not raw_query.strip():
        return []

    clean_q = re.sub(r'[\(\)\[\]\{\}]', '', raw_query).strip()
    api_key = os.environ.get("STEAMGRIDDB_API_KEY", "").strip()
    results: List[Dict[str, Any]] = []

    if api_key:
        try:
            auth_headers = {**BROWSER_HEADERS, "Authorization": f"Bearer {api_key}"}
            q_enc = urllib.parse.quote(clean_q)
            auto_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{q_enc}"
            req = urllib.request.Request(auto_url, headers=auth_headers)
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                games = data.get("data", [])
                for g_entry in games:
                    game_id = g_entry.get("id")
                    game_name = g_entry.get("name", clean_q)
                    if not _is_candidate_relevant(game_name, "", "", clean_q):
                        continue
                    if game_id:
                        grids_url = f"https://www.steamgriddb.com/api/v2/grids/game/{game_id}?dimensions=600x900,512x512,1024x1024"
                        g_req = urllib.request.Request(grids_url, headers=auth_headers)
                        with urllib.request.urlopen(g_req, timeout=1.8) as g_resp:
                            g_data = json.loads(g_resp.read().decode("utf-8", errors="ignore"))
                            for item in g_data.get("data", [])[:max_results]:
                                full_u = item.get("url")
                                thumb_u = item.get("thumb") or full_u
                                w = item.get("width", 600)
                                h = item.get("height", 900)
                                if full_u:
                                    results.append({
                                        "id": f"sgdb_{item.get('id', len(results))}",
                                        "name": game_name,
                                        "poster_url": full_u,
                                        "thumb_url": thumb_u,
                                        "is_square": (w == h),
                                        "is_vertical": (h >= w),
                                        "source": "SteamGridDB",
                                        "pre_verified": True
                                    })
                        break
            if results:
                return results
        except Exception:
            pass

    # Fallback 0-config: Búsqueda de alta resolución verificando coincidencia estricta con el juego
    try:
        q_enc = urllib.parse.quote(f"{clean_q} steamgriddb cover poster")
        url = f"https://www.bing.com/images/search?q={q_enc}&qft=+filterui:imagesize-large&form=HDRSC2&first=1"
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        seen = set()
        with urllib.request.urlopen(req, timeout=1.8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            matches = re.findall(r'class="iusc"[^>]*m="([^"]+)"', html)
            for m in matches:
                raw_json = m.replace('&quot;', '"').replace('&amp;', '&')
                try:
                    data = json.loads(raw_json)
                    murl = data.get("murl")
                    turl = data.get("turl")
                    title = data.get("t", clean_q)
                    desc = data.get("desc", "")
                    if not murl or murl in seen:
                        continue
                    if not _is_candidate_relevant(title, murl, desc, clean_q):
                        continue
                    seen.add(murl)
                    results.append({
                        "id": f"sgdb_web_{len(results)}",
                        "name": title,
                        "poster_url": murl,
                        "thumb_url": turl or murl,
                        "is_square": False,
                        "is_vertical": True,
                        "source": "SteamGridDB",
                        "pre_verified": True
                    })
                    if len(results) >= max_results:
                        break
                except Exception:
                    pass
    except Exception:
        pass

    return results

def search_cover_candidates(raw_query: str, max_results: int = 24) -> List[Dict[str, Any]]:
    """
    Busca de manera ultra rápida carátulas oficiales, key art y wallpapers 1080p/HD
    explícitamente relacionados con el juego consultando simultáneamente:
      1. Steam Store (Carátulas verticales 600x900_2x y Hero/Header Key Art HD).
      2. Google / Web Covers & Key Art HD (+filterui:imagesize-large).
      3. Google / Web Wallpapers 1080p HD del juego (adaptables al cuadro 3D).
      4. SteamGridDB y GOG Catalog (filtrados estrictamente por el juego).
    """
    if not raw_query or not raw_query.strip():
        return []

    query = raw_query.strip()
    cleaned = clean_game_name(query)
    simplified = re.sub(
        r'\b(202\d|resynced|remastered|deluxe|version|edition|remake|collection|repack|pack|dlc)\b',
        '',
        cleaned or query,
        flags=re.IGNORECASE
    )
    simplified = re.sub(r'\s+', ' ', simplified).strip()
    primary_term = simplified or cleaned or query

    cache_key = ("cover", primary_term.lower())
    if cache_key in _CANDIDATES_CACHE:
        return [dict(item) for item in _CANDIDATES_CACHE[cache_key][:max_results]]

    def _fetch_google_covers():
        try:
            return search_google_web_covers(primary_term, max_results=14)
        except Exception:
            return []

    def _fetch_google_hd_wallpapers_for_cover():
        try:
            wp_items = search_google_web_wallpapers(primary_term, max_results=12)
            adapted_list = []
            for item in wp_items:
                c_item = dict(item)
                c_item["id"] = f"cov_hd1080_{len(adapted_list)}"
                c_item["source"] = "Key Art 1080p HD"
                adapted_list.append(c_item)
            return adapted_list
        except Exception:
            return []

    def _fetch_steam():
        steam_res = []
        try:
            params = urllib.parse.urlencode({
                "query": "",
                "start": 0,
                "count": 12,
                "term": primary_term,
                "category1": "998",
                "infinite": 1
            })
            req_url = f"{STEAM_INFINITE_URL}?{params}"
            req = urllib.request.Request(req_url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                html = data.get("results_html", "")
                appids = re.findall(r'data-ds-appid="(\d+)"', html)
                titles = re.findall(r'<span class="title">([^<]+)</span>', html)
                for aid_str, t in zip(appids, titles):
                    try:
                        aid = int(aid_str)
                        clean_t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").strip()
                        if not _is_candidate_relevant(clean_t, "", "", primary_term):
                            continue
                        hd_2x = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/library_600x900_2x.jpg"
                        hd_1x = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/library_600x900.jpg"
                        steam_res.append({
                            "id": aid,
                            "name": clean_t,
                            "poster_url": hd_2x,
                            "thumb_url": hd_1x,
                            "is_square": False,
                            "is_vertical": True,
                            "source": "Steam Oficial",
                            "pre_verified": True
                        })
                        # Añadir también el Key Art apaisado HD oficial de Steam para poder encuadrarlo como carátula
                        hero_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/library_hero.jpg"
                        header_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                        steam_res.append({
                            "id": f"{aid}_hero",
                            "name": f"{clean_t} (Key Art HD)",
                            "poster_url": hero_url,
                            "thumb_url": header_url,
                            "is_square": False,
                            "is_vertical": False,
                            "is_widescreen": True,
                            "source": "Steam HD 16:9",
                            "pre_verified": True
                        })
                        if len(steam_res) >= 8:
                            break
                    except Exception:
                        pass
        except Exception:
            pass
        return steam_res

    def _fetch_gog():
        gog_res = []
        try:
            params = urllib.parse.urlencode({
                "limit": 8,
                "locale": "es-ES",
                "order": "desc:score",
                "query": primary_term
            })
            gog_url = f"{GOG_CATALOG_URL}?{params}"
            req = urllib.request.Request(gog_url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                gog_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                for prod in gog_data.get("products", []):
                    title = prod.get("title", "")
                    if not _is_candidate_relevant(title, "", "", primary_term):
                        continue
                    cover_v = prod.get("coverVertical")
                    prod_id = f"gog_{prod.get('id', title)}"
                    if cover_v:
                        gog_res.append({
                            "id": prod_id,
                            "name": title,
                            "poster_url": cover_v,
                            "thumb_url": cover_v,
                            "is_square": False,
                            "is_vertical": True,
                            "source": "GOG Oficial",
                            "pre_verified": True
                        })
        except Exception:
            pass
        return gog_res

    found_urls = set()
    valid_candidates: List[Dict[str, Any]] = []

    def _add_candidate(cand: Dict[str, Any]):
        u = cand.get("poster_url")
        if u and u not in found_urls:
            found_urls.add(u)
            valid_candidates.append(cand)

    with ThreadPoolExecutor(max_workers=5) as executor:
        f_steam = executor.submit(_fetch_steam)
        f_google_cov = executor.submit(_fetch_google_covers)
        f_google_wp = executor.submit(_fetch_google_hd_wallpapers_for_cover)
        f_sgdb = executor.submit(search_steamgriddb_covers, primary_term, 6)
        f_gog = executor.submit(_fetch_gog)

        for sr in f_steam.result():
            _add_candidate(sr)

        for gr in f_gog.result():
            _add_candidate(gr)

        cov_list = f_google_cov.result()
        wp_list = f_google_wp.result()
        sgdb_list = f_sgdb.result()

        # Intercalar carátulas/key art HD con wallpapers 1080p HD y grids de SteamGridDB
        # para que desde las primeras filas el usuario tenga tanto portadas verticales como arte 1080p del juego
        max_len = max(len(cov_list), len(wp_list), len(sgdb_list), 0)
        for idx_i in range(max_len):
            if idx_i < len(cov_list):
                _add_candidate(cov_list[idx_i])
            if idx_i < len(wp_list):
                _add_candidate(wp_list[idx_i])
            if idx_i < len(sgdb_list):
                _add_candidate(sgdb_list[idx_i])

    if valid_candidates:
        _CANDIDATES_CACHE[cache_key] = [dict(x) for x in valid_candidates]

    return valid_candidates[:max_results]

def download_and_save_cover(
    img_url: str,
    target_file_path: str,
    fallback_url: Optional[str] = None,
    fit_mode: str = "auto",
    crop_anchor: str = "center",
    crop_offset: Optional[float] = None
) -> bool:
    """
    Descarga una imagen desde cualquier URL (Google / Web, Steam, GOG),
    la valida con Pillow, la adapta al formato cuadrado de borde a borde (sin bandas laterales)
    según el modo elegido en la vista previa y la guarda atómicamente de forma instantánea.
    """
    from core.coverflow_engine import adapt_cover_to_square

    urls_to_try = [img_url]
    if fallback_url and fallback_url != img_url:
        urls_to_try.append(fallback_url)

    for idx_u, u in enumerate(urls_to_try):
        t_out = 3.2 if idx_u == 0 and len(urls_to_try) > 1 else 4.5
        try:
            req = urllib.request.Request(u, headers=IMAGE_REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=t_out) as resp:
                if resp.status == 200:
                    raw_bytes = _safe_read_response(resp)
                    if len(raw_bytes) > 1024:
                        with Image.open(io.BytesIO(raw_bytes)) as raw_im:
                            converted = adapt_cover_to_square(
                                raw_im.convert("RGBA"),
                                size=600,
                                fit_mode=fit_mode,
                                crop_anchor=crop_anchor,
                                crop_offset=crop_offset
                            )
                            os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
                            tmp_out = f"{target_file_path}.tmp"
                            converted.save(tmp_out, "PNG", compress_level=1)
                        os.replace(tmp_out, target_file_path)
                        return True
        except Exception:
            continue

    print(f"[CoverDownloader] Error descargando portada desde {img_url}")
    return False

def fetch_image_from_url(url: str, fallback_url: Optional[str] = None, timeout: float = 2.5) -> Optional[Image.Image]:
    """Descarga una imagen en memoria y la retorna como objeto PIL Image para vistas previas rápidas."""
    urls_to_try = [url]
    if fallback_url and fallback_url != url:
        urls_to_try.append(fallback_url)

    for u in urls_to_try:
        try:
            req = urllib.request.Request(u, headers=IMAGE_REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    raw_bytes = _safe_read_response(resp)
                    if len(raw_bytes) > 800:
                        with Image.open(io.BytesIO(raw_bytes)) as im:
                            return im.convert("RGBA").copy()
        except Exception:
            pass
    return None


def search_google_web_wallpapers(raw_query: str, max_results: int = 24) -> List[Dict[str, Any]]:
    """
    Busca wallpapers apaisados (16:9 / widescreen) estrictamente 1080p o superior (1920x1080, 2K, 4K)
    en una única petición ultrarrápida (~400ms) para el fondo ambiental de Big Picture.
    """
    if not raw_query or not raw_query.strip():
        return []

    query = raw_query.strip()
    clean_q = re.sub(r'[\(\)\[\]\{\}]', '', query).strip()
    q_enc = urllib.parse.quote(f"{clean_q} game wallpaper 1920x1080")
    url = f"https://www.bing.com/images/search?q={q_enc}&qft=+filterui:aspect-wide&form=HDRSC2&first=1"
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    seen_urls = set()
    results: List[Dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=2.2) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            matches = re.findall(r'class="iusc"[^>]*?m="([^"]+)"(?:[^>]*?href="([^"]+)")?', html)
            for m, href in matches:
                raw_json = m.replace('&quot;', '"').replace('&amp;', '&')
                try:
                    data = json.loads(raw_json)
                    murl = data.get("murl")
                    turl = data.get("turl")
                    title = data.get("t", clean_q)
                    desc = data.get("desc", "")
                    if not murl or murl in seen_urls:
                        continue
                    if not _is_candidate_relevant(title, murl, desc, clean_q):
                        continue

                    # Extraer resolución real informada por Bing (expw x exph)
                    w_match = re.search(r'expw=(\d+)', href or "")
                    h_match = re.search(r'exph=(\d+)', href or "")
                    w = int(w_match.group(1)) if w_match else 0
                    h = int(h_match.group(1)) if h_match else 0

                    # Filtro estricto 1080p+: Descartar miniaturas, 720p o imágenes <1080 (ej. 474x266, 460x215)
                    if w > 0 and h > 0:
                        if h < 1080 or w < 1920:
                            continue
                    else:
                        # Si no vinieron dimensiones explícitas, verificar si la URL/título indica 1080p/4K
                        lower_combined = f"{murl} {title}".lower()
                        if any(res_kw in lower_combined for res_kw in ["1080", "1920", "4k", "uhd", "2160", "2560", "1440"]):
                            w, h = 1920, 1080
                        else:
                            # Sin confirmación de 1080p, descartar para garantizar 100% pureza de alta resolución
                            continue

                    lower_m = murl.lower()
                    if any(ext in lower_m for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "image" in lower_m or "wallpaper" in lower_m:
                        seen_urls.add(murl)
                        results.append({
                            "id": f"wp_web_{len(results)}",
                            "name": title,
                            "poster_url": murl,
                            "thumb_url": turl or murl,
                            "orig_size": (w, h),
                            "width": w,
                            "height": h,
                            "is_1080p": True,
                            "is_square": False,
                            "is_vertical": False,
                            "is_widescreen": True,
                            "source": "Wallpaper 1080p",
                            "desc": desc,
                            "pre_verified": True
                        })
                        if len(results) >= max_results:
                            break
                except Exception:
                    pass
    except Exception:
        pass

    return results


def search_wallpaper_candidates(raw_query: str, max_results: int = 24) -> List[Dict[str, Any]]:
    """
    Busca de forma ultra rápida wallpapers apaisados (16:9) estrictamente 1080p o superior (1920x1080, 2K, 4K)
    combinando en paralelo fuentes web y oficiales de alta definición.
    """
    if not raw_query or not raw_query.strip():
        return []

    query = raw_query.strip()
    cleaned = clean_game_name(query)
    simplified = re.sub(
        r'\b(202\d|resynced|remastered|deluxe|version|edition|remake|collection|repack|pack|dlc)\b',
        '',
        cleaned or query,
        flags=re.IGNORECASE
    )
    simplified = re.sub(r'\s+', ' ', simplified).strip()
    primary_term = simplified or cleaned or query

    cache_key = ("wallpaper_1080", primary_term.lower())
    if cache_key in _CANDIDATES_CACHE:
        return [dict(item) for item in _CANDIDATES_CACHE[cache_key][:max_results]]

    def _fetch_google_wp():
        try:
            return search_google_web_wallpapers(primary_term, max_results=max_results)
        except Exception:
            return []

    def _fetch_steam_wp():
        steam_res = []
        try:
            params = urllib.parse.urlencode({
                "query": "",
                "start": 0,
                "count": 12,
                "term": primary_term,
                "category1": "998",
                "infinite": 1
            })
            req_url = f"{STEAM_INFINITE_URL}?{params}"
            req = urllib.request.Request(req_url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                html = data.get("results_html", "")
                appids = re.findall(r'data-ds-appid="(\d+)"', html)
                titles = re.findall(r'<span class="title">([^<]+)</span>', html)
                for aid_str, t in zip(appids, titles):
                    try:
                        aid = int(aid_str)
                        clean_t = t.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'").strip()
                        if not _is_candidate_relevant(clean_t, "", "", primary_term):
                            continue
                        hero_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/library_hero.jpg"
                        header_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg"
                        steam_res.append({
                            "id": f"steam_wp_{aid}",
                            "name": clean_t,
                            "poster_url": hero_url,
                            "thumb_url": header_url,
                            "is_square": False,
                            "is_vertical": False,
                            "is_widescreen": True,
                            "source": "Steam 16:9",
                            "pre_verified": True
                        })
                        if len(steam_res) >= 8:
                            break
                    except Exception:
                        pass
        except Exception:
            pass
        return steam_res

    def _fetch_gog_wp():
        gog_res = []
        try:
            params = urllib.parse.urlencode({
                "limit": 8,
                "locale": "es-ES",
                "order": "desc:score",
                "query": primary_term
            })
            gog_url = f"{GOG_CATALOG_URL}?{params}"
            req = urllib.request.Request(gog_url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                gog_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                for prod in gog_data.get("products", []):
                    title = prod.get("title", "")
                    if not _is_candidate_relevant(title, "", "", primary_term):
                        continue
                    cover_h = prod.get("coverHorizontal")
                    prod_id = f"gog_wp_{prod.get('id', title)}"
                    if cover_h:
                        gog_res.append({
                            "id": prod_id,
                            "name": title,
                            "poster_url": cover_h,
                            "thumb_url": cover_h,
                            "is_square": False,
                            "is_vertical": False,
                            "is_widescreen": True,
                            "source": "GOG 16:9",
                            "pre_verified": True
                        })
        except Exception:
            pass
        return gog_res

    found_keys = set()
    valid_candidates: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_google = executor.submit(_fetch_google_wp)
        f_steam = executor.submit(_fetch_steam_wp)
        f_gog = executor.submit(_fetch_gog_wp)

        for wr in f_google.result():
            k = wr["poster_url"]
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(wr)

        for sr in f_steam.result():
            k = sr["id"]
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(sr)

        for gr in f_gog.result():
            k = gr["id"]
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(gr)

    # Filtrar estrictamente solo wallpapers de 1080p o superior (altura >= 1080 y ancho >= 1920)
    only_1080_candidates: List[Dict[str, Any]] = []
    for cand in valid_candidates:
        orig_sz = cand.get("orig_size")
        if orig_sz:
            if orig_sz[1] < 1080 or orig_sz[0] < 1920:
                continue
        only_1080_candidates.append(cand)

    final_results = only_1080_candidates if only_1080_candidates else valid_candidates

    if final_results:
        _CANDIDATES_CACHE[cache_key] = [dict(x) for x in final_results]

    return final_results[:max_results]


def download_and_save_wallpaper(
    img_url: str,
    target_file_path: str,
    fallback_url: Optional[str] = None,
    crop_offset: float = 0.5
) -> bool:
    """
    Descarga un wallpaper apaisado desde cualquier URL, lo adapta a 1920x1080 (16:9)
    y lo guarda atómicamente en disco de forma instantánea.
    """
    from core.coverflow_engine import adapt_wallpaper_to_widescreen

    urls_to_try = [img_url]
    if fallback_url and fallback_url != img_url:
        urls_to_try.append(fallback_url)

    for idx_u, u in enumerate(urls_to_try):
        t_out = 3.2 if idx_u == 0 and len(urls_to_try) > 1 else 4.5
        try:
            req = urllib.request.Request(u, headers=IMAGE_REQ_HEADERS)
            with urllib.request.urlopen(req, timeout=t_out) as resp:
                if resp.status == 200:
                    raw_bytes = _safe_read_response(resp)
                    if len(raw_bytes) > 1024:
                        with Image.open(io.BytesIO(raw_bytes)) as raw_im:
                            converted = adapt_wallpaper_to_widescreen(
                                raw_im.convert("RGB"),
                                width=1920,
                                height=1080,
                                crop_offset=crop_offset
                            )
                            os.makedirs(os.path.dirname(os.path.abspath(target_file_path)), exist_ok=True)
                            tmp_out = f"{target_file_path}.tmp"
                            converted.save(tmp_out, "PNG", compress_level=1)
                        os.replace(tmp_out, target_file_path)
                        return True
        except Exception:
            continue

    print(f"[CoverDownloader] Error descargando wallpaper desde {img_url}")
    return False


def fetch_steamgriddb_best_assets(
    raw_name: str,
    exe_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Consulta la API pública oficial de SteamGridDB (0-config, sin requerir API key)
    para encontrar la mejor carátula vertical (grid 600x900) y fondo horizontal (hero 1920x620 / 1080p).
    """
    if not raw_name or not raw_name.strip():
        return None

    clean = re.sub(r'[\(\)\[\]\{\}]', '', raw_name).strip()
    simplified = re.sub(
        r'\b(202\d|resynced|repack|pack|dlc|unreal|unity|edition|version|remake|remastered)\b',
        '',
        clean,
        flags=re.IGNORECASE
    ).strip()
    simplified = re.sub(r'\s+', ' ', simplified)

    queries_to_try = [clean]
    if simplified and simplified.lower() != clean.lower():
        queries_to_try.append(simplified)

    # Si hay ruta de ejecutable, extraer también el nombre de la carpeta contenedora como fallback
    if exe_path and os.path.exists(exe_path):
        folder_name = os.path.basename(os.path.dirname(os.path.abspath(exe_path)))
        if folder_name and folder_name.lower() not in ('binaries', 'win64', 'win32', 'x64', 'retail', 'game'):
            folder_clean = re.sub(r'[\(\)\[\]\{\}]', '', folder_name).strip()
            if folder_clean and folder_clean.lower() not in [q.lower() for q in queries_to_try]:
                queries_to_try.append(folder_clean)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://www.steamgriddb.com/",
        "Accept": "application/json, text/plain, */*"
    }

    game_id = None
    matched_title = ""

    for q in queries_to_try:
        try:
            q_enc = urllib.parse.quote(q)
            url = f"https://www.steamgriddb.com/api/public/search/autocomplete?term={q_enc}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                items = data.get("data", [])
                if items:
                    game_id = items[0]["id"]
                    matched_title = items[0]["name"]
                    break
        except Exception:
            continue

    if not game_id:
        return None

    try:
        home_url = f"https://www.steamgriddb.com/api/public/game/{game_id}/home"
        req = urllib.request.Request(home_url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore")).get("data", {})
            grids = data.get("grids", [])
            heroes = data.get("heroes", [])

            grid_url = None
            for g in grids:
                gw = g.get("width", 600)
                gh = g.get("height", 900)
                if gh >= gw and g.get("url"):
                    grid_url = g["url"]
                    break

            hero_url = None
            for h in heroes:
                hw = h.get("width", 1920)
                hh = h.get("height", 620)
                if hw > hh and h.get("url"):
                    hero_url = h["url"]
                    break

            return {
                "game_id": game_id,
                "matched_name": matched_title,
                "grid_url": grid_url,
                "hero_url": hero_url
            }
    except Exception:
        return None


def download_and_apply_steamgriddb_media(
    game: Dict[str, Any],
    download_cover: bool = True,
    download_wallpaper: bool = True,
    overwrite: bool = True
) -> Dict[str, Any]:
    """
    Descarga y aplica automáticamente las carátulas y wallpapers oficiales de SteamGridDB
    para un juego específico, adaptándolos a los estándares de visualización del lanzador.
    """
    name = game.get("name", "Juego")
    path = game.get("path", "")
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip() or "game"

    assets = fetch_steamgriddb_best_assets(name, path)
    if not assets:
        return {
            "success": False,
            "error": "Juego no encontrado en SteamGridDB",
            "matched_name": None,
            "cover_applied": False,
            "wallpaper_applied": False
        }

    matched_name = assets.get("matched_name") or name
    cover_applied = False
    wallpaper_applied = False

    # 1. Carátula vertical 3D (Grid)
    if download_cover and assets.get("grid_url"):
        existing_cover = game.get("cover")
        if overwrite or not existing_cover or not os.path.isfile(existing_cover):
            target_cover = os.path.join(COVERS_DIR, f"{safe_name}.png")
            if download_and_save_cover(assets["grid_url"], target_cover, fit_mode="auto"):
                game["cover"] = target_cover
                cover_applied = True

    # 2. Wallpaper horizontal 16:9 (Hero)
    if download_wallpaper and assets.get("hero_url"):
        existing_wp = game.get("wallpaper")
        if overwrite or not existing_wp or not os.path.isfile(existing_wp):
            target_wp = os.path.join(WALLPAPERS_DIR, f"{safe_name}_wallpaper.png")
            if download_and_save_wallpaper(assets["hero_url"], target_wp):
                game["wallpaper"] = target_wp
                if "wallpaper_opacity" not in game:
                    game["wallpaper_opacity"] = 0.75
                if "wallpaper_blur" not in game:
                    game["wallpaper_blur"] = 0.0
                wallpaper_applied = True

    return {
        "success": cover_applied or wallpaper_applied,
        "matched_name": matched_name,
        "cover_applied": cover_applied,
        "wallpaper_applied": wallpaper_applied
    }

