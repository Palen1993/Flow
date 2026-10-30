import os
import re
from typing import List, Dict, Any, Optional

from core.cover_resolver import resolve_game_cover

IGNORE_DIRS = {
    '_commonredist', 'redist', 'directx', 'support', 'prerequisites', 
    'engine', 'tools', 'dotnet', 'installers', 'dependencies', 
    'bonus', 'soundtrack', 'artbook', 'manual', '__installer', 
    'easyanticheat', 'battleye', 'crashreporter', 'mono', 'licenses',
    'crashdumps', 'logs', 'temp', 'tmp', 'cache', '.git', '.vscode',
    '$recycle.bin', 'system volume information'
}

IGNORE_EXE_EXACT = {
    'unins000.exe', 'unins001.exe', 'uninstall.exe', 'uninst.exe', 'setup.exe', 
    'installer.exe', 'inst.exe', 'cleanup.exe', 'dxsetup.exe', 'oalinst.exe', 
    'physx.exe', 'easyanticheat.exe', 'easyanticheat_eos_setup.exe', 'battleye.exe', 
    'beservice.exe', 'crashreportclient.exe', 'unitycrashhandler64.exe', 
    'unitycrashhandler32.exe', 'reporter.exe', 'error_report.exe', 'feedback.exe', 
    '7z.exe', 'cmd.exe', 'ffmpeg.exe', 'quickbms.exe', 'benchmark.exe', 'register.exe'
}

GENERIC_SUBDIRS = {
    'bin', 'binaries', 'game', 'engine', 'data', 'client', 'system', 
    'win32', 'win64', 'x64', 'x86', 'build', 'release', 'content', 
    'assets', 'r6', 'archive', 'idsoftware', 'base', 'shipping'
}

def clean_game_name(raw_name: str) -> str:
    """Limpia nombres de carpetas eliminando tags de versión, repack, corchetes, etc."""
    name = raw_name
    # 1. Eliminar contenido entre corchetes o paréntesis típicos de scene/repack/ROMs
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'\(.*?\)', '', name)
    
    # 2. Eliminar palabras clave comunes de la scene
    scene_words = [
        r'\bFitGirl\b', r'\bDODI\b', r'\bCODEX\b', r'\bSKIDROW\b', r'\bREPACK\b',
        r'\bMULTi\d+\b', r'\bv\d+(\.\d+)*\b', r'\bBuild\s*\d+\b', r'\bGOG\b',
        r'\bPROPHET\b', r'\bPLAZA\b', r'\bCPY\b', r'\bRAZOR1911\b', r'\bSteamRip\b',
        r'\bPortable\b', r'\bCrack\b', r'\bRip\b'
    ]
    for pattern in scene_words:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
        
    # 3. Reemplazar guiones bajos y puntos por espacios (si no son decimales)
    name = name.replace('_', ' ')
    name = re.sub(r'\.(?!\d)', ' ', name)
    
    # 4. Limpiar espacios extra y caracteres no deseados en extremos
    name = re.sub(r'\s+', ' ', name).strip(" -_.,()[]{}")
    
    # Si quedó vacío o demasiado corto, usar el original
    if not name or len(name) < 2:
        name = raw_name.strip()
        
    return name

def score_candidate_exe(exe_path: str, base_dir: str, folder_name: str) -> float:
    """Evalúa la probabilidad de que un archivo .exe sea el ejecutable principal del juego."""
    score = 0.0
    file_name = os.path.basename(exe_path)
    name_no_ext, _ = os.path.splitext(file_name)
    name_lower = name_no_ext.lower()
    folder_clean = clean_game_name(folder_name).lower()
    
    if (name_lower + ".exe") in IGNORE_EXE_EXACT or name_lower in IGNORE_EXE_EXACT:
        return -9999.0
        
    for bad in ['unins', 'uninstall', 'vcredist', 'dxsetup', 'crash', 'reporter', 
                'anti-cheat', 'anticheat', 'handler', 'prereq', 'patch', 'cleanup', 'eac_', 'bootstrapper', 'eosbootstrapper', 'redist']:
        if bad in name_lower:
            return -9999.0

    # Tamaño del archivo
    try:
        size_bytes = os.path.getsize(exe_path)
        size_mb = size_bytes / (1024 * 1024)
        if size_mb < 0.2:
            score -= 20.0
        else:
            score += min(50.0, size_mb * 2.0)
    except Exception:
        pass

    # Profundidad de ruta desde base_dir
    try:
        rel = os.path.relpath(exe_path, base_dir)
        parts = rel.replace('\\', '/').split('/')
        depth = len(parts) - 1
        if depth == 0:
            score += 45.0  # Justo en la raíz del juego
        elif depth == 1:
            score += 30.0
        elif depth == 2:
            score += 20.0
        else:
            score -= 15.0
            
        rel_lower = rel.lower().replace('\\', '/')
        if any(p in rel_lower for p in ['/bin/', '/x64/', '/win64/', '/game/', 'binaries/']):
            score += 35.0
    except Exception:
        pass

    # Coincidencia con el nombre de la carpeta
    clean_no_space = folder_clean.replace(" ", "")
    name_no_space = name_lower.replace(" ", "").replace("_", "").replace("-", "")
    
    if name_lower == folder_clean or (clean_no_space and name_no_space == clean_no_space):
        score += 100.0
    elif folder_clean and folder_clean in name_lower:
        score += 70.0
    elif len(name_lower) > 3 and name_lower in folder_clean:
        score += 50.0

    # Coincidencia con acrónimos (ej: GTA5 -> Grand Theft Auto V, RDR2 -> Red Dead Redemption 2)
    words = [w for w in re.split(r'[^a-zA-Z0-9]+', folder_clean) if w]
    if len(words) > 1:
        acronym = "".join(w[0] for w in words).lower()
        if acronym and (acronym == name_lower or acronym in name_lower):
            score += 55.0

    # Palabras clave positivas
    if 'shipping' in name_lower or 'game' in name_lower:
        score += 25.0
    if 'launcher' in name_lower:
        score += 15.0

    # Palabras clave negativas
    if any(k in name_lower for k in ['config', 'settings', 'server', 'editor', 'tool', 'test', 'register', 'updater', 'cef', 'helper']):
        score -= 70.0

    return score

def find_executables_in_dir(directory: str, max_depth: int = 3) -> List[str]:
    """Busca archivos .exe recursivamente hasta cierta profundidad evitando carpetas basura."""
    found_exes = []
    base_level = directory.rstrip('\\/').count(os.sep)
    for root, dirs, files in os.walk(directory):
        current_level = root.count(os.sep)
        # Podar carpetas ignoradas
        dirs[:] = [
            d for d in dirs 
            if d.lower() not in IGNORE_DIRS 
            and not d.startswith('.') 
            and not d.startswith('$')
            and (current_level - base_level < max_depth)
        ]
        for f in files:
            if f.lower().endswith('.exe'):
                found_exes.append(os.path.join(root, f))
    return found_exes

def scan_directory_for_games(root_dir: str, existing_paths: Optional[set] = None) -> List[Dict[str, Any]]:
    """Escanea una carpeta en busca de juegos, retornando una lista de diccionarios con info de juego."""
    if not os.path.isdir(root_dir):
        return []
        
    if existing_paths is None:
        existing_paths = set()
        
    steam_common = os.path.join(root_dir, "steamapps", "common")
    if os.path.isdir(steam_common):
        root_dir = steam_common

    results = []
    added_exe_paths = set()
    
    try:
        sub_items = os.listdir(root_dir)
    except Exception:
        return []
        
    sub_dirs = [
        d for d in sub_items 
        if os.path.isdir(os.path.join(root_dir, d)) 
        and d.lower() not in IGNORE_DIRS 
        and not d.startswith('.') and not d.startswith('$')
    ]
    
    # Determinar si root_dir es un único juego
    is_single_game = False
    if not sub_dirs:
        is_single_game = True
    else:
        all_generic = all(d.lower() in GENERIC_SUBDIRS for d in sub_dirs)
        root_name = os.path.basename(os.path.abspath(root_dir))
        root_exes = [
            f for f in os.listdir(root_dir) 
            if f.lower().endswith('.exe') and os.path.isfile(os.path.join(root_dir, f))
        ]
        if all_generic or any(clean_game_name(root_name).lower() in f.lower() for f in root_exes):
            is_single_game = True

    if is_single_game:
        all_exes = find_executables_in_dir(root_dir, max_depth=3)
        folder_name = os.path.basename(os.path.abspath(root_dir))
        scored = []
        for exe in all_exes:
            s = score_candidate_exe(exe, root_dir, folder_name)
            if s > 0:
                scored.append((s, exe))
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            best_exe = scored[0][1]
            game_name = clean_game_name(folder_name)
            fake_game = {"name": game_name, "path": best_exe}
            cover_path = resolve_game_cover(fake_game, root_dir=root_dir, force_rescan=False)
            norm_path = os.path.normcase(os.path.abspath(best_exe))
            is_already_added = norm_path in existing_paths
            results.append({
                "name": game_name,
                "path": best_exe,
                "cover": cover_path,
                "monitor": 0,
                "high_priority": True,
                "already_added": is_already_added
            })
    else:
        # Escanear cada subdirectorio como posible juego
        for sub in sub_dirs:
            sub_path = os.path.join(root_dir, sub)
            exes = find_executables_in_dir(sub_path, max_depth=3)
            scored = []
            for exe in exes:
                s = score_candidate_exe(exe, sub_path, sub)
                if s > 0:
                    scored.append((s, exe))
            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                best_exe = scored[0][1]
                norm_path = os.path.normcase(os.path.abspath(best_exe))
                if norm_path not in added_exe_paths:
                    added_exe_paths.add(norm_path)
                    game_name = clean_game_name(sub)
                    if game_name.lower() in ("epic games", "steam", "gog", "games", "juegos"):
                        exe_base = os.path.splitext(os.path.basename(best_exe))[0]
                        game_name = clean_game_name(exe_base)
                    fake_game = {"name": game_name, "path": best_exe}
                    cover_path = resolve_game_cover(fake_game, root_dir=sub_path, force_rescan=False)
                    is_already_added = norm_path in existing_paths
                    results.append({
                        "name": game_name,
                        "path": best_exe,
                        "cover": cover_path,
                        "monitor": 0,
                        "high_priority": True,
                        "already_added": is_already_added
                    })
                    
        # Además, buscar ejecutables sueltos en root_dir
        root_loose_exes = [
            os.path.join(root_dir, f) for f in os.listdir(root_dir) 
            if f.lower().endswith('.exe') and os.path.isfile(os.path.join(root_dir, f))
        ]
        for exe in root_loose_exes:
            s = score_candidate_exe(exe, root_dir, os.path.basename(exe))
            if s > 10:
                norm_path = os.path.normcase(os.path.abspath(exe))
                if norm_path not in added_exe_paths:
                    added_exe_paths.add(norm_path)
                    name_no_ext, _ = os.path.splitext(os.path.basename(exe))
                    game_name = clean_game_name(name_no_ext)
                    fake_game = {"name": game_name, "path": exe}
                    cover_path = resolve_game_cover(fake_game, root_dir=root_dir, force_rescan=False)
                    is_already_added = norm_path in existing_paths
                    results.append({
                        "name": game_name,
                        "path": exe,
                        "cover": cover_path,
                        "monitor": 0,
                        "high_priority": True,
                        "already_added": is_already_added
                    })

    return results

def get_detected_games_folders(existing_games: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    r"""
    Identifica de forma automática e inteligente las carpetas principales de juegos del usuario:
    1. Carpetas deducidas de los juegos ya registrados en games.json (ej: D:\Juegos)
    2. Rutas estándar en discos locales (D:\Juegos, C:\Juegos, D:\Games, etc.)
    3. Rutas personalizadas guardadas previamente.
    """
    folders: List[str] = []
    seen: set = set()

    # 1. Analizar juegos existentes en la biblioteca
    for g in (existing_games or []):
        p = g.get("path")
        if p and os.path.isabs(p):
            norm_p = os.path.normpath(p)
            parts = norm_p.split(os.sep)
            if len(parts) >= 3:
                cand_folder = os.path.join(parts[0] + os.sep, parts[1])
                cand_norm = os.path.normcase(os.path.abspath(cand_folder))
                if os.path.isdir(cand_folder) and cand_norm not in seen:
                    cand_lower = cand_norm.lower()
                    if "program files" not in cand_lower and "windows" not in cand_lower and "appdata" not in cand_lower:
                        seen.add(cand_norm)
                        folders.append(cand_folder)

    # 2. Rutas comunes en unidades de almacenamiento locales
    for drive_letter in ["D", "C", "E", "F", "G"]:
        for name in ["Juegos", "Games"]:
            cand = f"{drive_letter}:\\{name}"
            cand_norm = os.path.normcase(os.path.abspath(cand))
            if os.path.isdir(cand) and cand_norm not in seen:
                seen.add(cand_norm)
                folders.append(cand)

    return folders

