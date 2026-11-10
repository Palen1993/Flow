import os
import ctypes
from typing import Optional, Dict, Any
from PIL import Image
try:
    import win32gui
    import win32ui
except ImportError:
    win32gui = None
    win32ui = None

from core.config import COVERS_DIR
from core.coverflow_engine import create_procedural_album

def extract_exe_icon(exe_path: str, size: int = 256) -> Optional[Image.Image]:
    """Extrae el icono de máxima resolución integrado en un .exe liberando todos los recursos GDI."""
    hicon = ctypes.c_void_p()
    desktop_dc = 0
    hdc = None
    hdc_mem = None
    hbmp = None
    if win32gui is None or win32ui is None:
        return None
    try:
        ico_x = size
        ico_y = size
        icon_id = ctypes.c_uint()
        res = ctypes.windll.user32.PrivateExtractIconsW(
            exe_path, 0, ico_x, ico_y, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0
        )
        if res > 0 and hicon.value:
            desktop_dc = win32gui.GetDC(0)
            hdc = win32ui.CreateDCFromHandle(desktop_dc)
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
            hdc_mem = hdc.CreateCompatibleDC()
            old_bmp = hdc_mem.SelectObject(hbmp)
            win32gui.DrawIconEx(hdc_mem.GetHandleOutput(), 0, 0, hicon.value, ico_x, ico_y, 0, 0, 3)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            img = Image.frombuffer('RGBA', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRA', 0, 1)
            return img.copy()
    except Exception:
        pass
    finally:
        # Liberación estricta en orden inverso Win32 GDI:
        # 1) Deseleccionar HBITMAP del DC de memoria, 2) Eliminar DC de memoria, 3) Eliminar HBITMAP, 4) Liberar DC de escritorio
        if hicon.value:
            try:
                ctypes.windll.user32.DestroyIcon(hicon.value)
            except Exception:
                pass
        if hdc_mem is not None:
            if old_bmp is not None:
                try:
                    hdc_mem.SelectObject(old_bmp)
                except Exception:
                    pass
            try:
                hdc_mem.DeleteDC()
            except Exception:
                pass
        if hbmp is not None:
            try:
                win32gui.DeleteObject(hbmp.GetHandle())
            except Exception:
                pass
        if desktop_dc:
            try:
                win32gui.ReleaseDC(0, desktop_dc)
            except Exception:
                pass
    return None

def load_icon_image(ico_path: str) -> Optional[Image.Image]:
    """Carga un archivo .ico seleccionando el frame de mayor resolución y convirtiéndolo a RGBA."""
    try:
        with Image.open(ico_path) as im:
            best_frame = 0
            max_pixels = im.size[0] * im.size[1]
            n_frames = getattr(im, 'n_frames', 1)
            if n_frames > 1:
                for i in range(n_frames):
                    try:
                        im.seek(i)
                        px = im.size[0] * im.size[1]
                        if px > max_pixels:
                            max_pixels = px
                            best_frame = i
                    except Exception:
                        pass
                im.seek(best_frame)
            return im.convert('RGBA')
    except Exception:
        pass
    return None

def score_ico_file(ico_path: str, game_name: str, exe_path: str) -> float:
    """Puntúa un archivo .ico para priorizar el icono principal del juego sobre utilidades."""
    score = 0.0
    f_lower = os.path.basename(ico_path).lower()
    
    # Descartar iconos no deseados
    if any(b in f_lower for b in ['unins', 'uninstall', 'setup', 'crash', 'report', 'helper', 'patch']):
        return -999.0
        
    clean_name = "".join(c for c in game_name.lower() if c.isalnum())
    clean_ico = "".join(c for c in os.path.splitext(f_lower)[0].lower() if c.isalnum())
    exe_clean = "".join(c for c in os.path.splitext(os.path.basename(exe_path))[0].lower() if c.isalnum())
    
    if clean_name and (clean_name in clean_ico or clean_ico in clean_name):
        score += 80.0
    if exe_clean and (exe_clean in clean_ico or clean_ico in exe_clean):
        score += 70.0
        
    if any(k in f_lower for k in ['game', 'icon', 'main', 'app', 'logo']):
        score += 25.0
        
    try:
        sz = os.path.getsize(ico_path)
        score += min(30.0, sz / 10000.0)
    except Exception:
        pass
        
    return score

def resolve_game_cover(
    game: Dict[str, Any],
    root_dir: Optional[str] = None,
    force_rescan: bool = False,
    target_path: Optional[str] = None
) -> str:
    """Busca o crea una carátula para el juego y guarda su ruta en disco."""
    os.makedirs(COVERS_DIR, exist_ok=True)
    safe_name = "".join(c for c in game.get("name", "game") if c.isalnum() or c in (' ', '_', '-')).strip()
    if not safe_name:
        safe_name = "game"
    target_cover_path = target_path or os.path.join(COVERS_DIR, f"{safe_name}.png")
    
    # 1. Si el juego ya tiene una carátula válida asignada y no forzamos reescaneo
    if not force_rescan and game.get("cover") and os.path.isfile(game["cover"]):
        return game["cover"]
        
    # Si target_cover_path ya existe en disco y no forzamos reescaneo
    if not force_rescan and os.path.isfile(target_cover_path):
        game["cover"] = target_cover_path
        return target_cover_path
        
    path = game.get("path", "")
    if path and os.path.exists(path):
        exe_path = os.path.abspath(path)
        exe_dir = os.path.dirname(exe_path)
        
        # Recopilar directorios: desde la carpeta del .exe subiendo hasta la raíz del juego
        dirs_to_check = [exe_dir]
        curr = exe_dir
        for _ in range(5):
            parent = os.path.dirname(curr)
            if not parent or parent == curr or os.path.splitdrive(parent)[1] in ('', '\\', '/'):
                break
            dirs_to_check.append(parent)
            if root_dir and os.path.abspath(curr) == os.path.abspath(root_dir):
                break
            if os.path.basename(parent).lower() in ('juegos', 'games', 'steamapps', 'common'):
                break
            curr = parent
            
        # Añadir subdirectorios típicos donde se guardan iconos y recursos
        extra_dirs = []
        for d in list(dirs_to_check):
            for sub in ['icon', 'icons', 'resource', 'resources', 'media', 'art', 'support']:
                sub_p = os.path.join(d, sub)
                if os.path.isdir(sub_p):
                    extra_dirs.append(sub_p)
        dirs_to_check.extend(extra_dirs)
        
        # 1. Buscar imágenes estándar en los directorios relevantes
        for d in dirs_to_check:
            for cand in ['cover.png', 'cover.jpg', 'cover.jpeg', 'poster.png', 'poster.jpg', 'boxart.png', 'boxart.jpg', 'logo.png', 'header.jpg', 'header.png']:
                cand_p = os.path.join(d, cand)
                if os.path.isfile(cand_p):
                    try:
                        with Image.open(cand_p) as raw_im:
                            im = raw_im.convert('RGBA')
                        im.save(target_cover_path)
                        game["cover"] = target_cover_path
                        return target_cover_path
                    except Exception:
                        pass
                        
        # 2. Buscar archivos .ico en todos los directorios relevantes (incluida la raíz del juego)
        ico_candidates = []
        for d in dirs_to_check:
            try:
                for f in os.listdir(d):
                    if f.lower().endswith('.ico'):
                        full_ico = os.path.join(d, f)
                        s = score_ico_file(full_ico, game.get("name", ""), exe_path)
                        if s > -500:
                            ico_candidates.append((s, full_ico))
            except Exception:
                pass
                
        if ico_candidates:
            ico_candidates.sort(key=lambda x: x[0], reverse=True)
            for _, best_ico in ico_candidates:
                ico_img = load_icon_image(best_ico)
                if ico_img:
                    try:
                        ico_img.save(target_cover_path)
                        game["cover"] = target_cover_path
                        return target_cover_path
                    except Exception:
                        game["cover"] = best_ico
                        return best_ico
                        
        # 3. Extraer icono del propio .exe
        exe_icon = extract_exe_icon(path, size=256)
        if exe_icon:
            exe_icon.save(target_cover_path)
            game["cover"] = target_cover_path
            return target_cover_path

    # 4. Fallback procedural estilo disco
    proc_cover = create_procedural_album(game.get("name", "Juego"), size=256)
    proc_cover.save(target_cover_path)
    game["cover"] = target_cover_path
    return target_cover_path
