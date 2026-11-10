"""
Cliente modular para consulta y descarga de carátulas (Grids) y fondos (Heroes)
desde SteamGridDB (API REST v2 oficial con API key o modo 0-config público).
"""
import os
import re
import json
import urllib.request
import urllib.parse
from typing import Optional, Dict, Any, List, Callable

from core.config import COVERS_DIR, WALLPAPERS_DIR, sanitize_game_filename

STEAMGRIDDB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Referer": "https://www.steamgriddb.com/",
    "Accept": "application/json, text/plain, */*"
}


def search_steamgriddb_covers_impl(
    raw_query: str,
    max_results: int,
    browser_headers: Dict[str, str],
    relevance_fn: Callable[[str, str, str, str], bool]
) -> List[Dict[str, Any]]:
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
            auth_headers = {**browser_headers, "Authorization": f"Bearer {api_key}"}
            q_enc = urllib.parse.quote(clean_q)
            auto_url = f"https://www.steamgriddb.com/api/v2/search/autocomplete/{q_enc}"
            req = urllib.request.Request(auto_url, headers=auth_headers)
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                games = data.get("data", [])
                for g_entry in games:
                    game_id = g_entry.get("id")
                    game_name = g_entry.get("name", clean_q)
                    if not relevance_fn(game_name, "", "", clean_q):
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
        req = urllib.request.Request(url, headers=browser_headers)
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
                    if not relevance_fn(title, murl, desc, clean_q):
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

    if exe_path and os.path.exists(exe_path):
        folder_name = os.path.basename(os.path.dirname(os.path.abspath(exe_path)))
        if folder_name and folder_name.lower() not in ('binaries', 'win64', 'win32', 'x64', 'retail', 'game'):
            folder_clean = re.sub(r'[\(\)\[\]\{\}]', '', folder_name).strip()
            if folder_clean and folder_clean.lower() not in [q.lower() for q in queries_to_try]:
                queries_to_try.append(folder_clean)

    game_id = None
    matched_title = ""

    for q in queries_to_try:
        try:
            q_enc = urllib.parse.quote(q)
            url = f"https://www.steamgriddb.com/api/public/search/autocomplete?term={q_enc}"
            req = urllib.request.Request(url, headers=STEAMGRIDDB_HEADERS)
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
        req = urllib.request.Request(home_url, headers=STEAMGRIDDB_HEADERS)
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
