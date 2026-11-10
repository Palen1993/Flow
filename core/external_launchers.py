import os
import re
import json
try:
    import winreg
except ImportError:
    winreg = None
from typing import List, Dict, Any, Optional, Set

from core.scanner import find_executables_in_dir, score_candidate_exe, clean_game_name
from core.cover_resolver import resolve_game_cover
from core.logger import get_logger

logger = get_logger("ExternalLaunchers")

# AppIDs de Steam que corresponden a herramientas o runtimes y no son juegos
STEAM_IGNORED_APPIDS = {
    "228980",  # Steamworks Common Redistributables
    "250820",  # SteamVR
    "1391110", # Steam Linux Runtime
    "1070560", # Steam Linux Runtime - Soldier
    "1628350", # Steam Linux Runtime - Sniper
    "894820",  # Steam Linux Runtime - Medic
    "2180100", # Steam Linux Runtime - Pressure Vessel
}

# Perfiles de emuladores populares y argumentos óptimos de pantalla completa
EMULATOR_PROFILES = {
    "RetroArch": {
        "exe_names": ["retroarch.exe"],
        "default_args": '-f -L "{core}" "{rom}"' if os.name == 'nt' else '-f "{rom}"',
        "rom_extensions": {".zip", ".7z", ".nes", ".sfc", ".smc", ".gba", ".gbc", ".n64", ".z64", ".cue", ".chd", ".iso"}
    },
    "RPCS3 (PlayStation 3)": {
        "exe_names": ["rpcs3.exe"],
        "default_args": '--no-gui "{rom}"',
        "rom_extensions": {".pkg", ".iso", ".bin"}
    },
    "PCSX2 (PlayStation 2)": {
        "exe_names": ["pcsx2-qtx64.exe", "pcsx2-qt.exe", "pcsx2.exe"],
        "default_args": '-nogui -fullscreen -- "{rom}"',
        "rom_extensions": {".iso", ".chd", ".bin", ".cso", ".gz"}
    },
    "Dolphin (GameCube / Wii)": {
        "exe_names": ["Dolphin.exe", "dolphin.exe"],
        "default_args": '-b -e "{rom}"',
        "rom_extensions": {".iso", ".rvz", ".gcm", ".wbfs", ".cso"}
    },
    "DuckStation (PlayStation 1)": {
        "exe_names": ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation.exe", "duckstation-qt.exe"],
        "default_args": '-fullscreen "{rom}"',
        "rom_extensions": {".iso", ".chd", ".cue", ".bin"}
    },
    "Cemu (Wii U)": {
        "exe_names": ["Cemu.exe", "cemu.exe"],
        "default_args": '-f -g "{rom}"',
        "rom_extensions": {".wua", ".rpx", ".wud", ".wux"}
    },
    "PPSSPP (PSP)": {
        "exe_names": ["PPSSPPWindows64.exe", "PPSSPP.exe", "PPSSPPWindows.exe"],
        "default_args": '--fullscreen "{rom}"',
        "rom_extensions": {".iso", ".cso", ".chd"}
    }
}


def _get_steam_install_path() -> Optional[str]:
    """Localiza la carpeta principal de instalación de Steam en Windows."""
    for root_key, subkey in [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam")
    ]:
        try:
            with winreg.OpenKey(root_key, subkey) as k:
                for val_name in ["SteamPath", "InstallPath"]:
                    try:
                        p, _ = winreg.QueryValueEx(k, val_name)
                        if p and os.path.isdir(p):
                            return os.path.normpath(p)
                    except Exception:
                        pass
        except Exception:
            pass

    for candidate in [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"E:\Steam"
    ]:
        if os.path.isdir(candidate):
            return candidate
    return None


def _get_steam_library_folders(steam_path: str) -> List[str]:
    """Extrae todas las carpetas de biblioteca de Steam a través de libraryfolders.vdf."""
    libraries = [steam_path]
    vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
    if not os.path.isfile(vdf_path):
        return libraries

    try:
        with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        paths = re.findall(r'"path"\s+"([^"]+)"', text)
        for p in paths:
            norm_p = os.path.normpath(p.replace("\\\\", "\\"))
            if os.path.isdir(norm_p) and norm_p not in libraries:
                libraries.append(norm_p)
    except Exception as e:
        logger.debug(f"Error analizando libraryfolders.vdf: {e}")
    return libraries


def get_steam_games(existing_paths: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """
    Descubre e importa juegos instalados en Steam analizando appmanifest_*.acf
    y enlazando carátulas oficiales 600x900 y wallpapers 16:9 de Steam CDN.
    """
    if existing_paths is None:
        existing_paths = set()

    steam_path = _get_steam_install_path()
    if not steam_path:
        return []

    libraries = _get_steam_library_folders(steam_path)
    found_games: List[Dict[str, Any]] = []
    seen_appids: Set[str] = set()

    for lib in libraries:
        steamapps = os.path.join(lib, "steamapps")
        if not os.path.isdir(steamapps):
            continue

        try:
            entries = os.listdir(steamapps)
        except Exception:
            continue

        for entry in entries:
            if not (entry.startswith("appmanifest_") and entry.endswith(".acf")):
                continue

            acf_path = os.path.join(steamapps, entry)
            try:
                with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()

                appid_m = re.search(r'"appid"\s+"([^"]+)"', content)
                name_m = re.search(r'"name"\s+"([^"]+)"', content)
                installdir_m = re.search(r'"installdir"\s+"([^"]+)"', content)

                if not (appid_m and name_m and installdir_m):
                    continue

                appid = appid_m.group(1).strip()
                raw_name = name_m.group(1).strip()
                installdir = installdir_m.group(1).strip()

                if appid in STEAM_IGNORED_APPIDS or appid in seen_appids:
                    continue
                seen_appids.add(appid)

                game_name = clean_game_name(raw_name)
                game_dir = os.path.join(steamapps, "common", installdir)
                if not os.path.isdir(game_dir):
                    continue

                # Buscar ejecutable principal inteligente
                exes = find_executables_in_dir(game_dir, max_depth=3)
                best_exe = None
                if exes:
                    scored = []
                    for exe in exes:
                        s = score_candidate_exe(exe, game_dir, installdir)
                        if s > 0:
                            scored.append((s, exe))
                    if scored:
                        scored.sort(key=lambda x: x[0], reverse=True)
                        best_exe = scored[0][1]

                launch_path = best_exe if best_exe else os.path.join(game_dir, f"{installdir}.exe")
                norm_launch = os.path.normcase(os.path.abspath(launch_path)) if launch_path else ""
                already_added = norm_launch in existing_paths

                # URLs oficiales en Cloudflare Steam CDN
                steam_cover_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg"
                steam_wallpaper_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/library_hero.jpg"

                fake_game = {"name": game_name, "path": launch_path}
                cover_local = resolve_game_cover(fake_game, root_dir=game_dir, force_rescan=False)

                found_games.append({
                    "name": game_name,
                    "path": launch_path,
                    "cover": cover_local,
                    "cover_url": steam_cover_url,
                    "wallpaper_url": steam_wallpaper_url,
                    "wallpaper_opacity": 0.28,
                    "wallpaper_blur": 1.5,
                    "monitor": 0,
                    "high_priority": True,
                    "platform": "Steam",
                    "platform_id": appid,
                    "already_added": already_added
                })
            except Exception as e:
                logger.debug(f"Error procesando manifest {entry}: {e}")

    logger.info(f"Steam: {len(found_games)} juego(s) detectado(s)")
    return found_games


def get_epic_games(existing_paths: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Descubre e importa juegos instalados en Epic Games Store analizando los manifiestos .item."""
    if existing_paths is None:
        existing_paths = set()

    manifests_dir = os.path.expandvars(r"%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests")
    if not os.path.isdir(manifests_dir):
        return []

    found_games: List[Dict[str, Any]] = []
    try:
        entries = os.listdir(manifests_dir)
    except Exception:
        return []

    for entry in entries:
        if not entry.lower().endswith(".item"):
            continue

        item_path = os.path.join(manifests_dir, entry)
        try:
            with open(item_path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)

            display_name = (data.get("DisplayName") or "").strip()
            install_loc = data.get("InstallLocation") or ""
            launch_exe = data.get("LaunchExecutable") or ""

            if not (display_name and install_loc and launch_exe):
                continue

            full_exe = os.path.normpath(os.path.join(install_loc, launch_exe))
            if not os.path.isfile(full_exe):
                continue

            game_name = clean_game_name(display_name)
            norm_exe = os.path.normcase(os.path.abspath(full_exe))
            already_added = norm_exe in existing_paths

            fake_game = {"name": game_name, "path": full_exe}
            cover_path = resolve_game_cover(fake_game, root_dir=install_loc, force_rescan=False)

            found_games.append({
                "name": game_name,
                "path": full_exe,
                "cover": cover_path,
                "monitor": 0,
                "high_priority": True,
                "platform": "Epic Games",
                "platform_id": data.get("AppName", ""),
                "already_added": already_added
            })
        except Exception as e:
            logger.debug(f"Error procesando manifest Epic {entry}: {e}")

    logger.info(f"Epic Games Store: {len(found_games)} juego(s) detectado(s)")
    return found_games


def get_gog_games(existing_paths: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Descubre e importa juegos instalados desde GOG Galaxy inspeccionando el Registro de Windows."""
    if existing_paths is None:
        existing_paths = set()

    found_games: List[Dict[str, Any]] = []
    for root_key, subkey_path in [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\GOG.com\Games"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\GOG.com\Games")
    ]:
        try:
            with winreg.OpenKey(root_key, subkey_path) as k:
                num_subkeys = winreg.QueryInfoKey(k)[0]
                for i in range(num_subkeys):
                    game_id = winreg.EnumKey(k, i)
                    try:
                        with winreg.OpenKey(k, game_id) as gk:
                            name, _ = winreg.QueryValueEx(gk, "gameName")
                            path, _ = winreg.QueryValueEx(gk, "path")
                            exe, _ = winreg.QueryValueEx(gk, "exe")
                            full_exe = os.path.normpath(os.path.join(path, exe))
                            if os.path.isfile(full_exe):
                                game_name = clean_game_name(name)
                                norm_exe = os.path.normcase(os.path.abspath(full_exe))
                                already_added = norm_exe in existing_paths

                                fake_game = {"name": game_name, "path": full_exe}
                                cover_path = resolve_game_cover(fake_game, root_dir=path, force_rescan=False)

                                found_games.append({
                                    "name": game_name,
                                    "path": full_exe,
                                    "cover": cover_path,
                                    "monitor": 0,
                                    "high_priority": True,
                                    "platform": "GOG Galaxy",
                                    "platform_id": str(game_id),
                                    "already_added": already_added
                                })
                    except Exception:
                        pass
        except Exception:
            pass

    logger.info(f"GOG Galaxy: {len(found_games)} juego(s) detectado(s)")
    return found_games


def scan_emulator_roms(
    emulator_exe: str,
    roms_dir: str,
    profile_name: str = "RetroArch",
    custom_args_template: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Escanea una carpeta de ROMs generando títulos de juego automáticos y asignando
    el emulador correspondiente como ejecutable con los argumentos de pantalla completa.
    """
    if not (os.path.isfile(emulator_exe) and os.path.isdir(roms_dir)):
        return []

    profile = EMULATOR_PROFILES.get(profile_name, {})
    valid_exts = profile.get("rom_extensions", {".iso", ".zip", ".chd", ".bin", ".rom"})
    args_template = custom_args_template or profile.get("default_args", '"{rom}"')

    rom_games: List[Dict[str, Any]] = []
    try:
        for root, _, files in os.walk(roms_dir):
            for file in files:
                _, ext = os.path.splitext(file)
                if ext.lower() in valid_exts:
                    full_rom_path = os.path.normpath(os.path.join(root, file))
                    base_name, _ = os.path.splitext(file)
                    game_name = clean_game_name(base_name)

                    # Formatear argumentos pasando la ruta absoluta de la ROM entrecomillada
                    launch_args = args_template.replace("{rom}", full_rom_path).replace("{core}", "")

                    fake_game = {"name": game_name, "path": full_rom_path}
                    cover_path = resolve_game_cover(fake_game, root_dir=root, force_rescan=False)

                    rom_games.append({
                        "name": game_name,
                        "path": emulator_exe,
                        "launch_args": launch_args,
                        "cover": cover_path,
                        "monitor": 0,
                        "high_priority": True,
                        "platform": profile_name,
                        "already_added": False
                    })
    except Exception as e:
        logger.error(f"Error escaneando ROMs en {roms_dir}: {e}", exc_info=True)

    logger.info(f"Emulador [{profile_name}]: {len(rom_games)} ROM(s) detectada(s)")
    return rom_games


def get_all_external_games(existing_paths: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Consulta de forma combinada e instantánea todos los lanzadores compatibles (Steam, Epic, GOG)."""
    results: List[Dict[str, Any]] = []
    results.extend(get_steam_games(existing_paths))
    results.extend(get_epic_games(existing_paths))
    results.extend(get_gog_games(existing_paths))
    return results
