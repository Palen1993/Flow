"""
GameFlow - Servicio de Modos de Energía y Perfiles de Rendimiento (Handheld Mode)
==================================================================================
Módulo especializado para consolas portátiles (ROG Ally, Steam Deck con Windows,
Lenovo Legion Go, AYANEO, GPD Win) y portátiles gaming.

Funcionalidades:
- Detección de modelo de dispositivo (ROG Ally, Legion Go, Steam Deck, etc.).
- Telemetría de batería del sistema y estado de alimentación AC (GetSystemPowerStatus).
- Control de perfiles de energía de Windows (powercfg / PowrProf):
  * 🌱 Modo Batería (Eco): Economizador, ~9-15W, ahorro máximo para indies/2D/retro.
  * ⚖️ Modo Equilibrado: Equilibrado, ~15-20W, balance ideal de temperatura y FPS.
  * ⚡ Modo Turbo: Alto Rendimiento, ~25-30W+, máxima fluidez para juegos AAA.
- Gestión de perfil preferido por juego (per-game profile) con restauración al salir.
"""

import os
import sys
import re
import subprocess
import ctypes
from ctypes import wintypes
from typing import Dict, Any, List, Optional, Tuple

try:
    from core.logger import get_logger
    logger = get_logger("PowerService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.PowerService")

from core.platform_layer import is_windows, winreg


# -----------------------------------------------------------------------------
# GUIDs estándar de planes de energía de Windows
# -----------------------------------------------------------------------------
GUID_POWER_SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"       # Economizador / Eco
GUID_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"          # Equilibrado
GUID_HIGH_PERFORMANCE = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"  # Alto Rendimiento / Turbo
GUID_ULTIMATE_PERF = "e9a42b02-d5df-448d-aa00-03f14749eb61"     # Máximo Rendimiento

# Definición de perfiles de rendimiento
POWER_PROFILES: Dict[str, Dict[str, Any]] = {
    "eco": {
        "id": "eco",
        "name": "Modo Batería (Eco)",
        "short_name": "Eco",
        "icon": "🌱",
        "color": "#10b981",          # Verde Esmeralda
        "border_color": "#059669",
        "guid": GUID_POWER_SAVER,
        "tdp_target": "~9W - 15W",
        "description": "Ahorro máximo de batería. Ideal para juegos 2D, emuladores retro y visual novels."
    },
    "balanced": {
        "id": "balanced",
        "name": "Modo Equilibrado",
        "short_name": "Equilibrado",
        "icon": "⚖️",
        "color": "#00d2ff",          # Cyan Accent
        "border_color": "#0088cc",
        "guid": GUID_BALANCED,
        "tdp_target": "~15W - 20W",
        "description": "Balance óptimo entre fluidez, temperaturas contenidas y ruido de ventiladores."
    },
    "turbo": {
        "id": "turbo",
        "name": "Modo Turbo (Rendimiento)",
        "short_name": "Turbo",
        "icon": "⚡",
        "color": "#f59e0b",          # Naranja / Ámbar Neón
        "border_color": "#d97706",
        "guid": GUID_HIGH_PERFORMANCE,
        "tdp_target": "~25W - 30W+",
        "description": "Máxima tasa de FPS y potencia de CPU/GPU desbloqueada para títulos AAA exigentes."
    }
}

_CURRENT_CACHED_MODE: Optional[str] = None
_PREVIOUS_SESSION_MODE: Optional[str] = None


# -----------------------------------------------------------------------------
# Estructura Win32 SYSTEM_POWER_STATUS
# -----------------------------------------------------------------------------
class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("Reserved1", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def get_system_battery_status() -> Dict[str, Any]:
    """
    Obtiene el estado de la batería del dispositivo y de la alimentación AC.
    Compatible con consolas portátiles (ROG Ally, Legion Go, Steam Deck) y ordenadores portátiles.
    """
    if not is_windows():
        # Stub para entornos de desarrollo y testing Linux/CI
        return {
            "has_battery": True,
            "ac_connected": True,
            "charging": False,
            "percent": 85,
            "remaining_minutes": 140,
            "status_label": "85% (Batería, ~2h 20m)",
            "icon": "🔋"
        }

    try:
        sps = SYSTEM_POWER_STATUS()
        if not hasattr(ctypes, "windll"):
            return _fallback_battery_dict()
        success = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps))
        if not success:
            return _fallback_battery_dict()

        ac_status = sps.ACLineStatus
        bat_flag = sps.BatteryFlag
        percent = int(sps.BatteryLifePercent)
        lifetime_sec = sps.BatteryLifeTime

        has_battery = (bat_flag != 128 and bat_flag != 255)
        ac_connected = (ac_status == 1)
        charging = bool(bat_flag & 8)

        if percent > 100:
            percent = 100 if has_battery else 0

        rem_min = (lifetime_sec // 60) if (lifetime_sec != 4294967295 and lifetime_sec > 0) else None

        if not has_battery:
            return {
                "has_battery": False,
                "ac_connected": True,
                "charging": False,
                "percent": 100,
                "remaining_minutes": None,
                "status_label": "Conectado a la corriente (PC de Escritorio)",
                "icon": "🔌"
            }

        if charging:
            label = f"{percent}% (Cargando ⚡)"
            icon = "⚡"
        elif ac_connected:
            label = f"{percent}% (Conectado a la red)"
            icon = "🔌"
        elif rem_min is not None and rem_min > 0:
            hours = rem_min // 60
            mins = rem_min % 60
            time_str = f"~{hours}h {mins}m" if hours > 0 else f"~{mins} min"
            label = f"{percent}% (Batería, {time_str})"
            icon = "🔋"
        else:
            label = f"{percent}% (Batería)"
            icon = "🔋"

        return {
            "has_battery": True,
            "ac_connected": ac_connected,
            "charging": charging,
            "percent": percent,
            "remaining_minutes": rem_min,
            "status_label": label,
            "icon": icon
        }
    except Exception as e:
        logger.warning(f"Error consultando GetSystemPowerStatus: {e}")
        return _fallback_battery_dict()


def _fallback_battery_dict() -> Dict[str, Any]:
    return {
        "has_battery": False,
        "ac_connected": True,
        "charging": False,
        "percent": 100,
        "remaining_minutes": None,
        "status_label": "Alimentación de Red",
        "icon": "🔌"
    }


# -----------------------------------------------------------------------------
# Detección de Dispositivo y Consolas Portátiles (Handhelds)
# -----------------------------------------------------------------------------
def get_device_model_info() -> Dict[str, Any]:
    """
    Detecta el fabricante y modelo del sistema para optimizar perfiles en
    ASUS ROG Ally, Valve Steam Deck, Lenovo Legion Go, AYANEO, GPD, etc.
    """
    manufacturer = "Desconocido"
    product_name = "PC Estándar"
    board_name = ""

    if is_windows():
        try:
            key_path = r"HARDWARE\DESCRIPTION\System\BIOS"
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            try:
                try:
                    manufacturer = str(winreg.QueryValueEx(hkey, "SystemManufacturer")[0]).strip()
                except Exception:
                    pass
                try:
                    product_name = str(winreg.QueryValueEx(hkey, "SystemProductName")[0]).strip()
                except Exception:
                    pass
                try:
                    board_name = str(winreg.QueryValueEx(hkey, "BaseBoardProduct")[0]).strip()
                except Exception:
                    pass
            finally:
                try:
                    winreg.CloseKey(hkey)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Lectura de BIOS en registro no disponible: {e}")

    full_sig = f"{manufacturer} {product_name} {board_name}".lower()

    is_handheld = False
    display_model = product_name
    brand_badge = "PC"

    # Detección de modelos de consolas portátiles
    if any(k in full_sig for k in ("rog ally", "rc71l", "rc72l")):
        is_handheld = True
        display_model = "ASUS ROG Ally"
        brand_badge = "ROG Ally"
    elif any(k in full_sig for k in ("steam deck", "jupiter", "galileo")):
        is_handheld = True
        display_model = "Valve Steam Deck"
        brand_badge = "Steam Deck"
    elif any(k in full_sig for k in ("legion go", "83e1")):
        is_handheld = True
        display_model = "Lenovo Legion Go"
        brand_badge = "Legion Go"
    elif any(k in full_sig for k in ("ayaneo", "air 1s", "kun", "geek")):
        is_handheld = True
        display_model = f"AYANEO ({product_name})"
        brand_badge = "AYANEO"
    elif any(k in full_sig for k in ("gpd", "win 4", "win max", "win mini")):
        is_handheld = True
        display_model = f"GPD ({product_name})"
        brand_badge = "GPD"
    elif any(k in full_sig for k in ("msi", "claw", "a1m")):
        is_handheld = True
        display_model = "MSI Claw"
        brand_badge = "MSI Claw"
    elif any(k in full_sig for k in ("onexplayer", "onexfly")):
        is_handheld = True
        display_model = "OneXPlayer"
        brand_badge = "OneXPlayer"
    else:
        # Si tiene batería integrada, es un portátil gaming o convertible
        bat = get_system_battery_status()
        if bat.get("has_battery"):
            display_model = f"{manufacturer} {product_name}".strip() or "Portátil Gaming"
            brand_badge = "Laptop"
        else:
            display_model = f"{manufacturer} {product_name}".strip() or "PC de Sobremesa"
            brand_badge = "Desktop"

    return {
        "manufacturer": manufacturer,
        "product_name": product_name,
        "display_name": display_model,
        "is_handheld": is_handheld,
        "badge": brand_badge
    }


# -----------------------------------------------------------------------------
# Gestión de Planes de Energía de Windows (powercfg)
# -----------------------------------------------------------------------------
def get_active_power_scheme_guid() -> Optional[str]:
    """Obtiene el GUID del plan de energía activo de Windows."""
    if not is_windows():
        mode = _CURRENT_CACHED_MODE or "balanced"
        return POWER_PROFILES.get(mode, {}).get("guid", GUID_BALANCED)

    try:
        kwargs = {"creationflags": 0x08000000} if is_windows() else {}
        out = subprocess.check_output(
            ["powercfg", "/getactivescheme"],
            text=True,
            timeout=3,
            **kwargs
        )
        match = re.search(r"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})", out, re.I)
        if match:
            return match.group(1).lower()
    except Exception as e:
        logger.warning(f"Error consultando powercfg /getactivescheme: {e}")

    return None


def get_current_power_mode() -> str:
    """Devuelve 'eco', 'balanced' o 'turbo' según el plan activo del sistema."""
    global _CURRENT_CACHED_MODE

    guid = get_active_power_scheme_guid()
    if not guid:
        return _CURRENT_CACHED_MODE or "balanced"

    guid_lower = guid.lower()
    if guid_lower == GUID_POWER_SAVER:
        _CURRENT_CACHED_MODE = "eco"
    elif guid_lower in (GUID_HIGH_PERFORMANCE, GUID_ULTIMATE_PERF):
        _CURRENT_CACHED_MODE = "turbo"
    else:
        _CURRENT_CACHED_MODE = "balanced"

    return _CURRENT_CACHED_MODE


def set_power_mode(mode: str) -> bool:
    """
    Aplica el plan de energía correspondiente ('eco', 'balanced' o 'turbo') mediante powercfg.
    No requiere privilegios de Administrador.
    """
    global _CURRENT_CACHED_MODE
    mode = (mode or "").lower().strip()
    if mode not in POWER_PROFILES:
        logger.warning(f"Modo de energía desconocido '{mode}', usando 'balanced'")
        mode = "balanced"

    profile = POWER_PROFILES[mode]
    target_guid = profile["guid"]

    if not is_windows():
        _CURRENT_CACHED_MODE = mode
        logger.info(f"[Mock] Modo de energía cambiado a '{profile['name']}' ({target_guid})")
        return True

    kwargs = {"creationflags": 0x08000000} if is_windows() else {}
    try:
        # Intentar activar directamente
        cmd = ["powercfg", "/setactive", target_guid]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4, **kwargs)
        if res.returncode == 0:
            _CURRENT_CACHED_MODE = mode
            logger.info(f"Plan de energía aplicado con éxito: {profile['name']}")
            return True

        # Si el plan no estaba duplicado en la instalación de Windows, intentar duplicarlo e instalarlo
        logger.info(f"Plan {target_guid} no presente, intentando duplicar...")
        dup_res = subprocess.run(
            ["powercfg", "/duplicatescheme", target_guid],
            capture_output=True,
            text=True,
            timeout=4,
            **kwargs
        )
        if dup_res.returncode == 0:
            set_res = subprocess.run(cmd, capture_output=True, text=True, timeout=4, **kwargs)
            if set_res.returncode == 0:
                _CURRENT_CACHED_MODE = mode
                logger.info(f"Plan de energía duplicado y activado: {profile['name']}")
                return True

        logger.warning(f"No se pudo activar el plan {target_guid}: {res.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error ejecutando powercfg /setactive: {e}")
        return False


# -----------------------------------------------------------------------------
# Integración de Perfil de Rendimiento por Juego
# -----------------------------------------------------------------------------
def apply_game_performance_profile(game: Dict[str, Any]) -> Optional[str]:
    """
    Aplica el perfil de energía configurado para el juego (si tiene uno específico: 'eco', 'balanced', 'turbo').
    Recuerda el perfil previo para poder restaurarlo al terminar la sesión.
    """
    global _PREVIOUS_SESSION_MODE
    game_mode = (game.get("performance_mode") or "default").lower().strip()

    if game_mode in ("eco", "balanced", "turbo"):
        _PREVIOUS_SESSION_MODE = get_current_power_mode()
        if _PREVIOUS_SESSION_MODE != game_mode:
            logger.info(f"Aplicando perfil por juego '{game_mode}' para '{game.get('name')}' (anterior: '{_PREVIOUS_SESSION_MODE}')")
            set_power_mode(game_mode)
        return _PREVIOUS_SESSION_MODE
    return None


def restore_previous_performance_profile() -> None:
    """Restaura el perfil de energía previo al iniciar el juego si fue modificado."""
    global _PREVIOUS_SESSION_MODE
    if _PREVIOUS_SESSION_MODE and _PREVIOUS_SESSION_MODE in POWER_PROFILES:
        current = get_current_power_mode()
        if current != _PREVIOUS_SESSION_MODE:
            logger.info(f"Restaurando perfil de energía previo al juego: '{_PREVIOUS_SESSION_MODE}'")
            set_power_mode(_PREVIOUS_SESSION_MODE)
        _PREVIOUS_SESSION_MODE = None
