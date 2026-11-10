import os
import sys
import math
import struct
import io
import time
import ctypes
from ctypes import wintypes
import threading
from core.platform_layer import winsound, is_windows, safe_play_sound
from typing import Optional

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(BASE_DIR, "assets", "sounds")
if not os.path.isdir(SOUNDS_DIR):
    _alt_sounds = os.path.join(BASE_DIR, "_internal", "assets", "sounds")
    if os.path.isdir(_alt_sounds):
        SOUNDS_DIR = _alt_sounds

# -------------------------------------------------------------
# Motor Háptico XInput (Rumble)
# -------------------------------------------------------------
class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [
        ("wLeftMotorSpeed", wintypes.WORD),   # Motor pesado / frecuencias bajas
        ("wRightMotorSpeed", wintypes.WORD),  # Motor fino / vibración háptica nítida
    ]

_xinput_dll = None
for _dll in ["xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"]:
    try:
        _xinput_dll = ctypes.windll.LoadLibrary(_dll)
        break
    except Exception:
        pass

def _send_vibration(slot: int, left: int, right: int):
    if not _xinput_dll:
        return
    try:
        vib = XINPUT_VIBRATION(wLeftMotorSpeed=left, wRightMotorSpeed=right)
        _xinput_dll.XInputSetState(slot, ctypes.byref(vib))
    except Exception:
        pass

def _send_vibration_all_slots(left: int, right: int):
    if not _xinput_dll:
        return
    vib = XINPUT_VIBRATION(wLeftMotorSpeed=left, wRightMotorSpeed=right)
    for s in range(4):
        try:
            _xinput_dll.XInputSetState(s, ctypes.byref(vib))
        except Exception:
            pass

_haptic_lock = threading.Lock()
_haptic_deadline = 0.0
_haptic_worker_running = False

def trigger_haptic(left: int = 18000, right: int = 36000, duration_ms: int = 60, slot: Optional[int] = None):
    """Dispara un pulso háptico de vibración en el mando de forma asíncrona sin bloquear la UI ni cortar pulsos solapados."""
    global _haptic_deadline, _haptic_worker_running
    try:
        from gamepad_manager import load_gamepad_config, get_active_xinput_slot
        cfg = load_gamepad_config()
        if not cfg.get("enable_haptics", True):
            return
        if slot is None:
            slot = get_active_xinput_slot()
    except Exception:
        pass

    if not _xinput_dll:
        return

    dur_sec = max(0.025, duration_ms / 1000.0)
    with _haptic_lock:
        _haptic_deadline = time.perf_counter() + dur_sec
        if slot is not None:
            _send_vibration(slot, left, right)
        else:
            _send_vibration_all_slots(left, right)

        if _haptic_worker_running:
            return
        _haptic_worker_running = True

    def _worker():
        global _haptic_worker_running
        try:
            while True:
                with _haptic_lock:
                    rem = _haptic_deadline - time.perf_counter()
                    if rem <= 0:
                        _send_vibration_all_slots(0, 0)
                        _haptic_worker_running = False
                        break
                time.sleep(min(0.015, max(0.004, rem)))
        except Exception:
            with _haptic_lock:
                _haptic_worker_running = False
            try:
                _send_vibration_all_slots(0, 0)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()

# -------------------------------------------------------------
# Generación Procedural de Sonidos Retro ("iPod Click" y Consola)
# -------------------------------------------------------------
def _generate_wav_file(path: str, samples: list, sample_rate: int = 44100):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw_pcm = bytearray()
        for s in samples:
            val = int(max(-32767, min(32767, s * 30000)))
            raw_pcm.extend(struct.pack('<h', val))

        with open(path, 'wb') as f:
            f.write(b'RIFF')
            f.write(struct.pack('<I', 36 + len(raw_pcm)))
            f.write(b'WAVEfmt ')
            f.write(struct.pack('<IHHIIHH', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
            f.write(b'data')
            f.write(struct.pack('<I', len(raw_pcm)))
            f.write(raw_pcm)
    except Exception:
        pass

def ensure_sound_assets(force_regenerate: bool = False):
    """Crea o actualiza los archivos de sonido en assets/sounds con tonos acústicos cálidos sin pitidos."""
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    click_path = os.path.join(SOUNDS_DIR, "click.wav")
    launch_path = os.path.join(SOUNDS_DIR, "launch.wav")
    menu_path = os.path.join(SOUNDS_DIR, "menu.wav")
    select_path = os.path.join(SOUNDS_DIR, "select.wav")
    sr = 44100

    # Auto-detectar si los archivos existentes en disco son las versiones obsoletas truncadas (< 3000 bytes)
    for p in [click_path, launch_path, menu_path, select_path]:
        if not os.path.isfile(p) or os.path.getsize(p) < 3000:
            force_regenerate = True
            break

    # 1. Clic táctil de carátula: suave 'tick' de vidrio/madera con cuerpo cálido (45ms)
    if force_regenerate or not os.path.isfile(click_path):
        click_samples = []
        for i in range(int(sr * 0.045)):
            t = i / sr
            attack = min(1.0, t / 0.0015)
            env = attack * math.exp(-t * 85.0)
            click_samples.append((0.55 * math.sin(2 * math.pi * 920 * t) + 
                                  0.35 * math.sin(2 * math.pi * 460 * t) + 
                                  0.15 * math.sin(2 * math.pi * 160 * t)) * env)
        _generate_wav_file(click_path, click_samples, sr)

    # 2. Acorde de lanzamiento cinematográfico cálido y profundo (180ms)
    if force_regenerate or not os.path.isfile(launch_path):
        launch_samples = []
        for i in range(int(sr * 0.180)):
            t = i / sr
            attack = min(1.0, t / 0.015)
            env = attack * math.exp(-t * 18.0)
            launch_samples.append((0.45 * math.sin(2 * math.pi * 220 * t) + 
                                   0.35 * math.sin(2 * math.pi * 330 * t) + 
                                   0.20 * math.sin(2 * math.pi * 440 * t)) * env)
        _generate_wav_file(launch_path, launch_samples, sr)

    # 3. Sonido sutil para selección de menús (38ms)
    if force_regenerate or not os.path.isfile(menu_path):
        menu_samples = []
        for i in range(int(sr * 0.038)):
            t = i / sr
            attack = min(1.0, t / 0.0015)
            env = attack * math.exp(-t * 95.0)
            menu_samples.append((0.60 * math.sin(2 * math.pi * 720 * t) + 
                                 0.35 * math.sin(2 * math.pi * 360 * t)) * env)
        _generate_wav_file(menu_path, menu_samples, sr)

    # 4. Pop cálido y agradable para confirmación / selección de carátulas (60ms)
    if force_regenerate or not os.path.isfile(select_path):
        select_samples = []
        for i in range(int(sr * 0.060)):
            t = i / sr
            attack = min(1.0, t / 0.002)
            env = attack * math.exp(-t * 60.0)
            select_samples.append((0.60 * math.sin(2 * math.pi * 540 * t) + 
                                   0.35 * math.sin(2 * math.pi * 270 * t) +
                                   0.15 * math.sin(2 * math.pi * 810 * t)) * env)
        _generate_wav_file(select_path, select_samples, sr)

def play_feedback_sound(name: str):
    """Reproduce de forma asíncrona y con latencia cero un sonido retro de la interfaz."""
    try:
        from gamepad_manager import load_gamepad_config
        cfg = load_gamepad_config()
        if not cfg.get("enable_sound_fx", True):
            return
    except Exception:
        pass

    sound_file = os.path.join(SOUNDS_DIR, f"{name}.wav")
    if not os.path.isfile(sound_file):
        ensure_sound_assets()

    if os.path.isfile(sound_file) and winsound:
        try:
            winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass

def feedback_click():
    """Dispara el clic mecánico clásico de iPod (sonido acústico cálido + pulso háptico nítido)."""
    play_feedback_sound("click")
    trigger_haptic(left=18000, right=38000, duration_ms=65)

def feedback_menu():
    """Dispara retroalimentación de navegación de menú."""
    play_feedback_sound("menu")
    trigger_haptic(left=14000, right=28000, duration_ms=45)

def feedback_select():
    """Dispara confirmación agradable y cálida sin pitidos."""
    play_feedback_sound("select")
    trigger_haptic(left=22000, right=42000, duration_ms=75)

def feedback_cover_applied():
    """Retroalimentación al aplicar carátula: suave 'pop' cálido + pulso háptico satisfactorio."""
    play_feedback_sound("select")
    trigger_haptic(left=26000, right=48000, duration_ms=85)

def feedback_launch():
    """Dispara retroalimentación de inicio de juego (acorde cálido + pulso firme)."""
    play_feedback_sound("launch")
    trigger_haptic(left=36000, right=56000, duration_ms=160)
