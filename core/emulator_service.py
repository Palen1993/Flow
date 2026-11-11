"""
GameFlow - Servicio de Emuladores y Lanzamiento de ROMs
======================================================
Módulo encargado de:
1. Catálogo universal de sistemas retro y plataformas de emulación.
2. Detección automática del sistema/consola basándose en la extensión de la ROM.
3. Limpieza inteligente de nombres de ROMs (eliminación de regiones, dumps, códigos de scene).
4. Detección de emuladores instalados en Windows (RetroArch, Dolphin, PCSX2, DuckStation, PPSSPP, RPCS3, Snes9x, mGBA, etc.).
5. Configuración persistente (emulators_config.json) para vincular sistemas a emuladores.
6. Construcción de comandos de ejecución y parámetros de pantalla completa.
7. Escaneo directo de carpetas de ROMs con extracción de metadatos.
"""

import os
import re
import sys
from typing import List, Dict, Any, Optional, Tuple

try:
    from core.config import get_storage_dir, save_json_atomic, sanitize_game_filename
    from core.logger import get_logger
    logger = get_logger("EmulatorService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.EmulatorService")

    def get_storage_dir() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def save_json_atomic(filepath: str, data: Any):
        import json
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)

    def sanitize_game_filename(name: str) -> str:
        return "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()


EMULATORS_CONFIG_FILE = "emulators_config.json"


# ==============================================================================
# BASE DE DATOS DE SISTEMAS RETRO Y EMULADORES
# ==============================================================================

SUPPORTED_SYSTEMS: List[Dict[str, Any]] = [
    {
        "id": "snes",
        "name": "Super Nintendo (SNES)",
        "icon": "🍄",
        "extensions": [".sfc", ".smc", ".fig"],
        "default_genre": "Plataformas y Metroidvania",
        "retroarch_cores": ["snes9x_libretro.dll", "mesen-s_libretro.dll", "bsnes_libretro.dll"],
        "standalone_executables": ["snes9x-x64.exe", "snes9x.exe", "bsnes.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "nes",
        "name": "Nintendo (NES)",
        "icon": "🕹️",
        "extensions": [".nes", ".unf", ".fds"],
        "default_genre": "Plataformas y Metroidvania",
        "retroarch_cores": ["fceumm_libretro.dll", "mesen_libretro.dll", "nestopia_libretro.dll"],
        "standalone_executables": ["fceux.exe", "Mesen.exe", "nestopia.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "n64",
        "name": "Nintendo 64",
        "icon": "🎮",
        "extensions": [".n64", ".z64", ".v64"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["mupen64plus_next_libretro.dll", "parallel_n64_libretro.dll"],
        "standalone_executables": ["Project64.exe", "mupen64plus.exe", "simple64.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "gamecube",
        "name": "Nintendo GameCube",
        "icon": "🐬",
        "extensions": [".gcm", ".rvz", ".gcz"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["dolphin_libretro.dll"],
        "standalone_executables": ["Dolphin.exe"],
        "args_template": "-b -e {rom}"
    },
    {
        "id": "wii",
        "name": "Nintendo Wii",
        "icon": "🎮",
        "extensions": [".wbfs", ".wia"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["dolphin_libretro.dll"],
        "standalone_executables": ["Dolphin.exe"],
        "args_template": "-b -e {rom}"
    },
    {
        "id": "gba",
        "name": "Game Boy Advance",
        "icon": "👾",
        "extensions": [".gba"],
        "default_genre": "Rol (RPG)",
        "retroarch_cores": ["mgba_libretro.dll", "vbam_libretro.dll"],
        "standalone_executables": ["mgba.exe", "VisualBoyAdvance.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "gb_gbc",
        "name": "Game Boy / Color",
        "icon": "📟",
        "extensions": [".gb", ".gbc"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["gambatte_libretro.dll", "mgba_libretro.dll"],
        "standalone_executables": ["mgba.exe", "bgb.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "nds",
        "name": "Nintendo DS",
        "icon": "📱",
        "extensions": [".nds"],
        "default_genre": "Rol (RPG)",
        "retroarch_cores": ["melonds_libretro.dll", "desmume_libretro.dll"],
        "standalone_executables": ["melonDS.exe", "DeSmuME.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "3ds",
        "name": "Nintendo 3DS",
        "icon": "🕶️",
        "extensions": [".3ds", ".cia"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["citra_libretro.dll"],
        "standalone_executables": ["citra-qt.exe", "citra.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "switch",
        "name": "Nintendo Switch",
        "icon": "🔴",
        "extensions": [".nsp", ".xci"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": [],
        "standalone_executables": ["Ryujinx.exe", "yuzu.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "ps1",
        "name": "PlayStation (PS1)",
        "icon": "💿",
        "extensions": [".chd", ".cue", ".pbp"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["swanstation_libretro.dll", "beetle_psx_hw_libretro.dll"],
        "standalone_executables": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation.exe", "epsxe.exe"],
        "args_template": "-batch -fullscreen {rom}"
    },
    {
        "id": "ps2",
        "name": "PlayStation 2 (PS2)",
        "icon": "📀",
        "extensions": [".cso"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["pcsx2_libretro.dll"],
        "standalone_executables": ["pcsx2-qtx64.exe", "pcsx2.exe"],
        "args_template": "-nogui -fullscreen -- {rom}"
    },
    {
        "id": "psp",
        "name": "PlayStation Portable (PSP)",
        "icon": "🎮",
        "extensions": [],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["ppsspp_libretro.dll"],
        "standalone_executables": ["PPSSPPWindows64.exe", "PPSSPP.exe"],
        "args_template": "-f {rom}"
    },
    {
        "id": "ps3",
        "name": "PlayStation 3 (PS3)",
        "icon": "🖤",
        "extensions": [".pkg"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": [],
        "standalone_executables": ["rpcs3.exe"],
        "args_template": "--no-gui {rom}"
    },
    {
        "id": "genesis",
        "name": "Sega Genesis / Mega Drive",
        "icon": "🦔",
        "extensions": [".md", ".smd", ".gen"],
        "default_genre": "Plataformas y Metroidvania",
        "retroarch_cores": ["genesis_plus_gx_libretro.dll", "picodrive_libretro.dll"],
        "standalone_executables": ["Fusion.exe", "blastem.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "dreamcast",
        "name": "Sega Dreamcast",
        "icon": "🌀",
        "extensions": [".cdi", ".gdi"],
        "default_genre": "Acción y Aventura",
        "retroarch_cores": ["flycast_libretro.dll"],
        "standalone_executables": ["flycast.exe", "redream.exe"],
        "args_template": "{rom}"
    },
    {
        "id": "arcade",
        "name": "Arcade (MAME / NeoGeo)",
        "icon": "🕹️",
        "extensions": [],
        "default_genre": "Lucha y Combate",
        "retroarch_cores": ["fbneo_libretro.dll", "mame_libretro.dll"],
        "standalone_executables": ["mame.exe", "mame64.exe"],
        "args_template": "{rom}"
    }
]

# Extensiones multipropósito (pueden pertenecer a varios sistemas)
MULTI_SYSTEM_EXTENSIONS = {
    ".iso": ["ps2", "gamecube", "wii", "ps1", "psp"],
    ".bin": ["ps1", "genesis", "arcade"],
    ".zip": ["arcade", "genesis", "snes", "nes"]
}


def get_all_supported_rom_extensions() -> List[str]:
    """Devuelve la lista unificada de todas las extensiones de ROM reconocidas."""
    exts = set()
    for sys_def in SUPPORTED_SYSTEMS:
        for e in sys_def["extensions"]:
            exts.add(e.lower())
    for e in MULTI_SYSTEM_EXTENSIONS.keys():
        exts.add(e.lower())
    return sorted(exts)


def detect_system_for_file(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Identifica el sistema/consola correspondiente analizando la extensión del archivo
    y heurísticas del nombre o ruta contenedora.
    """
    if not filepath:
        return None

    _, ext = os.path.splitext(filepath)
    ext = ext.lower().strip()
    if not ext:
        return None

    # 1. Coincidencia directa unívoca
    for sys_def in SUPPORTED_SYSTEMS:
        if ext in sys_def["extensions"]:
            return sys_def

    # 2. Extensión multi-sistema (ej: .iso, .bin, .zip) -> Desambiguación por nombre de carpeta
    if ext in MULTI_SYSTEM_EXTENSIONS:
        candidates = MULTI_SYSTEM_EXTENSIONS[ext]
        norm_path = filepath.lower().replace("\\", "/")
        for cand_id in candidates:
            if cand_id in norm_path or cand_id.replace("_", "") in norm_path:
                for sys_def in SUPPORTED_SYSTEMS:
                    if sys_def["id"] == cand_id:
                        return sys_def
        # Si no hay pista en la ruta, usar el primer candidato prioritario
        first_id = candidates[0]
        for sys_def in SUPPORTED_SYSTEMS:
            if sys_def["id"] == first_id:
                return sys_def

    return None


def clean_rom_name(raw_name: str) -> str:
    """
    Limpia el nombre de archivo de una ROM eliminando códigos de región (USA, Europe, Japan),
    versiones, hashes GoodTools/No-Intro ([!], [b1], (v1.1), (Track 1)), etc.
    Ejemplo: 'Super Mario World (USA).sfc' -> 'Super Mario World'
    """
    if not raw_name:
        return ""

    base_name = os.path.splitext(os.path.basename(raw_name))[0]

    # Eliminar corchetes [!] [b1] [T+Eng] etc.
    name = re.sub(r'\[.*?\]', '', base_name)

    # Eliminar paréntesis con regiones, versiones o revisiones típicas
    name = re.sub(
        r'\((USA|Europe|Japan|World|Spain|En|Fr|De|Es|It|Rev\s*\w+|v\d+(\.\d+)*|Beta|Proto|Sample|Demo|Track\s*\d+).*?\)',
        '',
        name,
        flags=re.IGNORECASE
    )

    # Eliminar cualquier otro paréntesis residual si contiene solo letras/dígitos cortos
    name = re.sub(r'\([A-Za-z0-9,\s\-]+\)', '', name)

    # Limpiar guiones bajos y puntos por espacios
    name = name.replace('_', ' ')
    name = re.sub(r'\.(?!\d)', ' ', name)

    # Limpiar espacios múltiples y extremos
    name = re.sub(r'\s+', ' ', name).strip(" -_.,()[]{}")

    return name if len(name) >= 2 else base_name.strip()


# ==============================================================================
# CONFIGURACIÓN Y DETECCIÓN DE EMULADORES
# ==============================================================================

def _get_config_path() -> str:
    return os.path.join(get_storage_dir(), EMULATORS_CONFIG_FILE)


def load_emulators_config(filepath: Optional[str] = None) -> Dict[str, Any]:
    """Carga la configuración persistente de emuladores del usuario."""
    cfg_p = filepath or _get_config_path()
    if os.path.isfile(cfg_p):
        try:
            import json
            with open(cfg_p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.warning(f"Error cargando {cfg_p}: {e}")

    return {
        "retroarch_path": "",
        "retroarch_cores_dir": "",
        "systems": {}
    }


def save_emulators_config(config: Dict[str, Any], filepath: Optional[str] = None) -> bool:
    """Guarda la configuración de emuladores atómicamente."""
    cfg_p = filepath or _get_config_path()
    try:
        save_json_atomic(cfg_p, config)
        logger.info("Configuración de emuladores guardada con éxito.")
        return True
    except Exception as e:
        logger.error(f"Error guardando {cfg_p}: {e}")
        return False


def detect_installed_emulators() -> Dict[str, List[str]]:
    """
    Busca emuladores conocidos instalados en Windows analizando directorios típicos:
    - Program Files, LocalAppData, AppData, C:\\RetroArch, C:\\Emuladores, etc.
    """
    results: Dict[str, List[str]] = {
        "retroarch": [],
        "standalone": []
    }

    search_roots = [
        r"C:\RetroArch",
        r"C:\RetroArch-Win64",
        r"C:\Emuladores",
        r"C:\Emulators",
        r"D:\Emuladores",
        r"D:\RetroArch",
        os.path.expandvars(r"%PROGRAMFILES%\RetroArch"),
        os.path.expandvars(r"%LOCALAPPDATA%\RetroArch"),
        os.path.expandvars(r"%APPDATA%\RetroArch"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
    ]

    seen = set()

    # 1. Buscar RetroArch
    for r in search_roots:
        if not os.path.isdir(r):
            continue
        ra_cand = os.path.join(r, "retroarch.exe")
        if os.path.isfile(ra_cand) and ra_cand.lower() not in seen:
            seen.add(ra_cand.lower())
            results["retroarch"].append(ra_cand)

    # 2. Buscar emuladores standalone conocidos
    known_exes = set()
    for sys_def in SUPPORTED_SYSTEMS:
        for ex in sys_def["standalone_executables"]:
            known_exes.add(ex.lower())

    for r in search_roots:
        if not os.path.isdir(r):
            continue
        try:
            for root, dirs, files in os.walk(r):
                # Limitar profundidad
                depth = root[len(r):].count(os.sep)
                if depth > 2:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower() in known_exes:
                        full_p = os.path.join(root, f)
                        if full_p.lower() not in seen:
                            seen.add(full_p.lower())
                            results["standalone"].append(full_p)
        except Exception:
            continue

    return results


def get_emulator_for_system(system_id: str) -> Optional[Dict[str, str]]:
    """
    Obtiene la ruta del emulador y argumentos recomendados para un sistema específico.
    Prioriza:
    1. Emulador específico configurado en emulators_config.json.
    2. RetroArch con el core correspondiente si existe.
    3. Emulador standalone detectado automáticamente.
    """
    cfg = load_emulators_config()
    sys_cfg = cfg.get("systems", {}).get(system_id, {})
    if sys_cfg.get("emulator_path") and os.path.isfile(sys_cfg["emulator_path"]):
        return {
            "path": sys_cfg["emulator_path"],
            "args_template": sys_cfg.get("args_template", "{rom}"),
            "type": "custom"
        }

    # Comprobar RetroArch
    ra_path = cfg.get("retroarch_path")
    if not ra_path or not os.path.isfile(ra_path):
        detected = detect_installed_emulators()
        if detected.get("retroarch"):
            ra_path = detected["retroarch"][0]

    sys_def = next((s for s in SUPPORTED_SYSTEMS if s["id"] == system_id), None)

    if ra_path and os.path.isfile(ra_path) and sys_def and sys_def.get("retroarch_cores"):
        cores_dir = cfg.get("retroarch_cores_dir") or os.path.join(os.path.dirname(ra_path), "cores")
        if os.path.isdir(cores_dir):
            for c in sys_def["retroarch_cores"]:
                core_p = os.path.join(cores_dir, c)
                if os.path.isfile(core_p):
                    return {
                        "path": ra_path,
                        "args_template": f'-L "{core_p}" {{rom}}',
                        "type": "retroarch"
                    }

    # Comprobar standalone detectado
    if sys_def and sys_def.get("standalone_executables"):
        detected_standalone = detect_installed_emulators().get("standalone", [])
        for stand_exe in sys_def["standalone_executables"]:
            for d in detected_standalone:
                if os.path.basename(d).lower() == stand_exe.lower() and os.path.isfile(d):
                    return {
                        "path": d,
                        "args_template": sys_def.get("args_template", "{rom}"),
                        "type": "standalone"
                    }

    return None


def build_rom_launch_command(
    rom_path: str,
    emulator_path: Optional[str] = None,
    system_id: Optional[str] = None,
    custom_args: Optional[str] = None
) -> Tuple[str, str]:
    """
    Construye la ruta del ejecutable y los argumentos para lanzar una ROM.
    Devuelve (executable_path, final_args_string).
    """
    abs_rom = os.path.abspath(rom_path)
    quoted_rom = f'"{abs_rom}"'

    sys_def = detect_system_for_file(rom_path)
    s_id = system_id or (sys_def["id"] if sys_def else "unknown")

    # 1. Si el usuario proporcionó un emulador explícito
    if emulator_path and os.path.isfile(emulator_path):
        if custom_args and "{rom}" in custom_args:
            final_args = custom_args.replace("{rom}", quoted_rom)
        elif custom_args:
            final_args = f"{custom_args.strip()} {quoted_rom}"
        else:
            tmpl = sys_def.get("args_template", "{rom}") if sys_def else "{rom}"
            final_args = tmpl.replace("{rom}", quoted_rom)
        return emulator_path, final_args

    # 2. Buscar emulador configurado o detectado
    emu_info = get_emulator_for_system(s_id)
    if emu_info:
        tmpl = custom_args or emu_info.get("args_template", "{rom}")
        if "{rom}" in tmpl:
            final_args = tmpl.replace("{rom}", quoted_rom)
        else:
            final_args = f"{tmpl.strip()} {quoted_rom}"
        return emu_info["path"], final_args

    # Fallback: Lanzar directamente la ROM (Windows la abrirá con el programa asociado por el usuario)
    return abs_rom, ""


def scan_folder_for_roms(
    folder_path: str,
    allowed_systems: Optional[List[str]] = None,
    recursive: bool = True
) -> List[Dict[str, Any]]:
    """
    Escanea una carpeta en busca de archivos ROM retro y genera la lista de juegos con metadatos.
    """
    if not os.path.isdir(folder_path):
        return []

    supported_exts = set(get_all_supported_rom_extensions())
    games: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(folder_path):
        if not recursive and os.path.abspath(root) != os.path.abspath(folder_path):
            break

        for f in sorted(files):
            _, ext = os.path.splitext(f)
            ext_lower = ext.lower()
            if ext_lower not in supported_exts:
                continue

            full_p = os.path.join(root, f)
            sys_info = detect_system_for_file(full_p)
            if not sys_info:
                continue

            if allowed_systems and sys_info["id"] not in allowed_systems:
                continue

            clean_title = clean_rom_name(f)
            platform_name = sys_info["name"]
            default_genre = sys_info.get("default_genre", "Acción y Aventura")

            # Buscar emulador sugerido
            emu_info = get_emulator_for_system(sys_info["id"])
            emu_path = emu_info["path"] if emu_info else ""
            launch_args = emu_info.get("args_template", "{rom}") if emu_info else ""

            games.append({
                "name": clean_title,
                "path": full_p,
                "platform": platform_name,
                "genre": default_genre,
                "is_rom": True,
                "system_id": sys_info["id"],
                "emulator_path": emu_path,
                "launch_args": launch_args,
                "collections": [f"Retro: {platform_name}"]
            })

    return games
