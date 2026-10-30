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

def search_google_web_covers(raw_query: str, max_results: int = 18) -> List[Dict[str, Any]]:
    """
    Busca carátulas en una única petición ultrarrápida (~400ms) priorizando formato cuadrado (1:1)
    y boxarts proporcionales en internet (PlayStation Store, Xbox, Epic, SteamGridDB, IGDB, MobyGames).
    """
    if not raw_query or not raw_query.strip():
        return []

    query = raw_query.strip()
    clean_q = re.sub(r'[\(\)\[\]\{\}]', '', query).strip()
    q_enc = urllib.parse.quote(f"{clean_q} game cover boxart")
    url = f"https://www.bing.com/images/search?q={q_enc}&form=HDRSC2&first=1"
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
                    lower_m = murl.lower()
                    if any(ext in lower_m for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "image" in lower_m or "upload" in lower_m or "cover" in lower_m or "box" in lower_m:
                        seen_urls.add(murl)
                        results.append({
                            "id": f"web_{len(results)}",
                            "name": title,
                            "poster_url": murl,
                            "thumb_url": turl or murl,
                            "is_square": False,
                            "is_vertical": True,
                            "source": "Google / Web",
                            "desc": desc
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
    Busca de manera ultra rápida carátulas oficiales y de internet consultando simultáneamente:
      1. Google / Web (Boxarts, carátulas de tiendas, mods, IGDB, MobyGames).
      2. Steam Store (Juegos completos, categoría 998).
      3. GOG Catalog (Pósters oficiales).
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

    # ---------------------------------------------------------
    # Búsqueda Concurrente Multiprovedor (Google + Steam + GOG)
    # ---------------------------------------------------------
    def _fetch_google():
        try:
            return search_google_web_covers(primary_term, max_results=16)
        except Exception:
            return []

    def _fetch_steam():
        steam_res = []
        query_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', primary_term))
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
                        t_words = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', clean_t))
                        if query_keywords and not (query_keywords & t_words):
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
                            "source": "Steam",
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
        query_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', primary_term))
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
                    title_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', title))
                    if query_keywords and not (query_keywords & title_keywords):
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
                            "source": "GOG",
                            "pre_verified": True
                        })
        except Exception:
            pass
        return gog_res

    found_keys = set()
    valid_candidates: List[Dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        f_google = executor.submit(_fetch_google)
        f_steam = executor.submit(_fetch_steam)
        f_gog = executor.submit(_fetch_gog)

        for wr in f_google.result():
            k = wr["poster_url"]
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(wr)

        for sr in f_steam.result():
            k = f"steam_{sr['id']}"
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(sr)

        for gr in f_gog.result():
            k = gr["id"]
            if k not in found_keys:
                found_keys.add(k)
                valid_candidates.append(gr)

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
                    raw_bytes = resp.read()
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
                    raw_bytes = resp.read()
                    if len(raw_bytes) > 800:
                        with Image.open(io.BytesIO(raw_bytes)) as im:
                            return im.convert("RGBA").copy()
        except Exception:
            pass
    return None


def search_google_web_wallpapers(raw_query: str, max_results: int = 18) -> List[Dict[str, Any]]:
    """
    Busca wallpapers apaisados (16:9 / widescreen) de alta resolución en una única petición ultrarrápida (~400ms)
    para el fondo ambiental de Big Picture.
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
                    lower_m = murl.lower()
                    if any(ext in lower_m for ext in [".jpg", ".jpeg", ".png", ".webp"]) or "image" in lower_m or "wallpaper" in lower_m:
                        seen_urls.add(murl)
                        results.append({
                            "id": f"wp_web_{len(results)}",
                            "name": title,
                            "poster_url": murl,
                            "thumb_url": turl or murl,
                            "is_square": False,
                            "is_vertical": False,
                            "is_widescreen": True,
                            "source": "Wallpaper 16:9",
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
    Busca de forma ultra rápida wallpapers apaisados (16:9) combinando en paralelo:
      1. Google / Web Widescreen 16:9 (1920x1080 / HD).
      2. Steam Library Hero y Header Artwork oficial apaisado.
      3. GOG Horizontal Artwork (coverHorizontal).
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

    cache_key = ("wallpaper", primary_term.lower())
    if cache_key in _CANDIDATES_CACHE:
        return [dict(item) for item in _CANDIDATES_CACHE[cache_key][:max_results]]

    def _fetch_google_wp():
        try:
            return search_google_web_wallpapers(primary_term, max_results=16)
        except Exception:
            return []

    def _fetch_steam_wp():
        steam_res = []
        query_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', primary_term))
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
                        t_words = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', clean_t))
                        if query_keywords and not (query_keywords & t_words):
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
        query_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', primary_term))
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
                    title_keywords = set(w.lower() for w in re.findall(r'[a-zA-Z0-9]{3,}', title))
                    if query_keywords and not (query_keywords & title_keywords):
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

    if valid_candidates:
        _CANDIDATES_CACHE[cache_key] = [dict(x) for x in valid_candidates]

    return valid_candidates[:max_results]


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
                    raw_bytes = resp.read()
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
