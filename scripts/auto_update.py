"""
Sincronización automática de GameFlow (Lanzador + Aplicación Personal).

Se ejecuta automáticamente al iniciar sesión en Windows (o manualmente) para:
1. Comprobar cambios en el repositorio remoto (origin/main) con reintentos de red.
2. Comparar marcas temporales cuando existen cambios locales y remotos:
   - Normalmente fusiona los cambios dando prioridad al remoto en conflictos.
   - Si los cambios locales (sin commit o commits locales) son más recientes que el
     último commit remoto, los commitea (verificando seguridad), fusiona y los sube.
3. Actualiza dependencias Python si requirements.txt cambió.
4. Recompila y actualiza la aplicación particular en:
   C:\\Users\\jorge\\Documents\\Programas\\GameFlow
   preservando siempre games.json, covers/, wallpapers/ y gamepad_config.json.
"""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

BASE_DEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DEV_DIR not in sys.path:
    sys.path.insert(0, BASE_DEV_DIR)

PLAYER_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(BASE_DEV_DIR), "GameFlow"))
CACHE_DIR = os.path.join(BASE_DEV_DIR, ".cache")
STATE_FILE = os.path.join(CACHE_DIR, "auto_update_state.json")
LOG_FILE = os.path.join(BASE_DEV_DIR, "auto_update.log")
BACKUPS_DIR = os.path.join(BASE_DEV_DIR, "backups")

STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VAL_NAME = "GameFlowAutoUpdate"

PERSONAL_FILES = {
    "games.json",
    "games.json.bak",
    "gamepad_config.json",
    "game_stats.json",
    "cloud_sync.json",
    "achievements_config.json",
    "achievements_cache.json",
    "collections_config.json",
    ".portable",
}
IGNORED_DIRTY_PREFIXES = (
    "scratch/",
    "covers/",
    "wallpapers/",
    "save_backups/",
    ".cache/",
    "backups/",
    "dist/",
    "build/",
    "venv/",
)
IGNORED_DIRTY_SUFFIXES = (".log", ".bak", ".lnk", ".tmp")


def log_msg(message: str, verbose: bool = False, log_file: str = LOG_FILE) -> None:
    """Registra un mensaje con marca temporal en auto_update.log y opcionalmente en stdout."""
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    if verbose:
        print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        if os.path.isfile(log_file) and os.path.getsize(log_file) > 512 * 1024:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-400:])
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _run_cmd(
    args: List[str],
    cwd: str,
    timeout: int = 180,
    extra_env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Ejecuta un subproceso sin ventana emergente en Windows y sin bloqueos interactivos."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra_env:
        env.update(extra_env)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=flags,
    )


def acquire_single_instance_mutex():
    """Evita ejecuciones simultáneas de auto_update.py mediante un Mutex de Windows."""
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        h_mutex = kernel32.CreateMutexW(None, False, "Local\\GameFlowAutoUpdateMutex")
        if kernel32.GetLastError() == 183:
            return False
        return h_mutex
    except Exception:
        return None


def is_ignored_dirty_path(rel_path: str) -> bool:
    """Filtra archivos personales, temporales o de scratch que nunca deben versionarse."""
    norm = rel_path.strip().replace("\\", "/").lstrip("./")
    low = norm.lower()
    if low in PERSONAL_FILES:
        return True
    if low in ("covers/.gitkeep", "wallpapers/.gitkeep"):
        return False
    if low.startswith(IGNORED_DIRTY_PREFIXES):
        return True
    if low.endswith(IGNORED_DIRTY_SUFFIXES):
        return True
    return False


def get_dirty_entries(repo_dir: str) -> List[Dict[str, object]]:
    """Obtiene los cambios locales sin commit (excluyendo scratch y archivos personales)."""
    res = _run_cmd(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=repo_dir)
    if res.returncode != 0:
        raise RuntimeError(f"git status falló: {res.stderr.strip()}")

    tokens = res.stdout.split("\0")
    entries: List[Dict[str, object]] = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        idx += 1
        if not token or len(token) < 4:
            continue
        status = token[:2]
        path = token[3:].replace("\\", "/")
        if status[0] in ("R", "C") or status[1] in ("R", "C"):
            # En formato -z, los renombrados/copias incluyen un segundo token con la ruta original
            idx += 1

        if is_ignored_dirty_path(path):
            continue

        abs_path = os.path.join(repo_dir, path.replace("/", os.sep))
        mtime = 0.0
        if os.path.exists(abs_path):
            try:
                mtime = os.path.getmtime(abs_path)
            except OSError:
                mtime = 0.0
        else:
            parent = os.path.dirname(abs_path)
            if os.path.isdir(parent):
                try:
                    mtime = os.path.getmtime(parent)
                except OSError:
                    mtime = 0.0

        entries.append({"status": status, "path": path, "mtime": mtime})
    return entries


def compute_dirty_signature(entries: List[Dict[str, object]]) -> str:
    """Calcula una firma estable del estado sucio actual para detectar si requiere recompilación."""
    if not entries:
        return ""
    payload = "|".join(
        f"{e['status']}:{e['path']}:{float(e['mtime']):.3f}"
        for e in sorted(entries, key=lambda x: str(x["path"]))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fetch_remote(
    repo_dir: str,
    remote: str = "origin",
    branch: str = "main",
    max_attempts: int = 6,
    delay_sec: float = 5.0,
    verbose: bool = False,
    log_file: str = LOG_FILE,
) -> bool:
    """Descarga referencias del remoto reintentando al inicio de sesión mientras arranca la red."""
    for attempt in range(1, max_attempts + 1):
        res = _run_cmd(["git", "fetch", remote, branch], cwd=repo_dir, timeout=60)
        if res.returncode == 0:
            return True
        err = (res.stderr or res.stdout).strip()
        log_msg(f"Intento {attempt}/{max_attempts} de git fetch falló: {err}", verbose, log_file)
        if attempt < max_attempts:
            time.sleep(delay_sec)
    return False


def inspect_repo_state(repo_dir: str, remote: str = "origin", branch: str = "main") -> Dict[str, object]:
    """Recopila hashes, conteo ahead/behind, marcas temporales y cambios locales."""
    remote_ref = f"{remote}/{branch}"
    head_res = _run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    rem_res = _run_cmd(["git", "rev-parse", remote_ref], cwd=repo_dir)
    if head_res.returncode != 0 or rem_res.returncode != 0:
        raise RuntimeError("No se pudo resolver HEAD o la rama remota.")

    local_head = head_res.stdout.strip()
    remote_head = rem_res.stdout.strip()

    counts_res = _run_cmd(
        ["git", "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"], cwd=repo_dir
    )
    if counts_res.returncode != 0:
        raise RuntimeError(f"git rev-list falló: {counts_res.stderr.strip()}")
    parts = counts_res.stdout.strip().split()
    local_ahead = int(parts[0])
    remote_behind = int(parts[1])

    rem_ts_res = _run_cmd(["git", "log", "-1", "--format=%ct", remote_ref], cwd=repo_dir)
    remote_ts = float(rem_ts_res.stdout.strip() or 0)

    unpushed_commit_ts = 0.0
    if local_ahead > 0:
        loc_ts_res = _run_cmd(["git", "log", "-1", "--format=%ct", "HEAD"], cwd=repo_dir)
        unpushed_commit_ts = float(loc_ts_res.stdout.strip() or 0)

    dirty_entries = get_dirty_entries(repo_dir)
    max_dirty_mtime = max((float(e["mtime"]) for e in dirty_entries), default=0.0)
    local_ts = max(unpushed_commit_ts, max_dirty_mtime)

    return {
        "local_head": local_head,
        "remote_head": remote_head,
        "local_ahead": local_ahead,
        "remote_behind": remote_behind,
        "remote_ts": remote_ts,
        "local_ts": local_ts,
        "dirty_entries": dirty_entries,
        "dirty_sig": compute_dirty_signature(dirty_entries),
    }


def _stage_and_commit_local(
    repo_dir: str,
    dirty_entries: List[Dict[str, object]],
    verbose: bool,
    log_file: str,
) -> bool:
    """Añade al stage únicamente los archivos seguros y crea un commit local."""
    paths = [str(e["path"]) for e in dirty_entries]
    if not paths:
        return False

    add_res = _run_cmd(["git", "add", "--"] + paths, cwd=repo_dir)
    if add_res.returncode != 0:
        raise RuntimeError(f"git add falló: {add_res.stderr.strip()}")

    verify_script = os.path.join(repo_dir, "scripts", "verify_clean_git.py")
    if os.path.isfile(verify_script):
        ver_res = _run_cmd([sys.executable, verify_script], cwd=repo_dir)
        if ver_res.returncode != 0:
            _run_cmd(["git", "reset", "HEAD"], cwd=repo_dir)
            raise RuntimeError(
                f"Bloqueado por verify_clean_git.py:\n{ver_res.stdout}\n{ver_res.stderr}".strip()
            )

    staged_res = _run_cmd(["git", "diff", "--cached", "--name-only"], cwd=repo_dir)
    if not staged_res.stdout.strip():
        return False

    msg = f"auto-sync(local): cambios locales mas recientes ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    commit_res = _run_cmd(["git", "commit", "-m", msg], cwd=repo_dir)
    if commit_res.returncode != 0:
        raise RuntimeError(f"git commit falló: {commit_res.stderr.strip() or commit_res.stdout.strip()}")

    log_msg(f"Commit local creado con {len(paths)} archivo(s) modificado(s).", verbose, log_file)
    return True


def _resolve_unmerged_conflicts(repo_dir: str, prefer: str, verbose: bool, log_file: str) -> None:
    """Resuelve conflictos restantes (p. ej. rename/delete) eligiendo 'ours' o 'theirs'."""
    unmerged_res = _run_cmd(["git", "diff", "--name-only", "--diff-filter=U"], cwd=repo_dir)
    unmerged = [p.strip() for p in unmerged_res.stdout.splitlines() if p.strip()]
    if not unmerged:
        return

    stage_num = "2" if prefer == "ours" else "3"
    flag = "--ours" if prefer == "ours" else "--theirs"
    for rel_path in unmerged:
        exists_in_side = _run_cmd(["git", "cat-file", "-e", f":{stage_num}:{rel_path}"], cwd=repo_dir)
        if exists_in_side.returncode == 0:
            _run_cmd(["git", "checkout", flag, "--", rel_path], cwd=repo_dir)
            _run_cmd(["git", "add", "--", rel_path], cwd=repo_dir)
        else:
            _run_cmd(["git", "rm", "-f", "--", rel_path], cwd=repo_dir)
    log_msg(f"Resueltos {len(unmerged)} conflicto(s) aplicando prioridad '{prefer}'.", verbose, log_file)


def _merge_remote(repo_dir: str, remote_ref: str, prefer: str, verbose: bool, log_file: str) -> None:
    """Fusiona remote_ref en HEAD usando -X ours o -X theirs y asegura commit limpio."""
    res = _run_cmd(["git", "merge", "--no-edit", "-X", prefer, remote_ref], cwd=repo_dir)
    if res.returncode == 0:
        return

    _resolve_unmerged_conflicts(repo_dir, prefer=prefer, verbose=verbose, log_file=log_file)
    fin = _run_cmd(["git", "commit", "--no-edit"], cwd=repo_dir)
    if fin.returncode != 0:
        _run_cmd(["git", "merge", "--abort"], cwd=repo_dir)
        raise RuntimeError(f"No se pudo completar el merge con {remote_ref}: {fin.stderr.strip()}")


def _save_stash_backup(repo_dir: str, backups_dir: str, verbose: bool, log_file: str) -> Optional[str]:
    """Guarda un parche de respaldo en backups/ antes de descartar conflictos en stash pop."""
    show_res = _run_cmd(["git", "stash", "show", "-p", "stash@{0}"], cwd=repo_dir)
    if show_res.returncode != 0 or not show_res.stdout.strip():
        return None
    os.makedirs(backups_dir, exist_ok=True)
    patch_path = os.path.join(
        backups_dir, f"auto_update_conflict_{datetime.now().strftime('%Y%m%d_%H%M%S')}.patch"
    )
    with open(patch_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(show_res.stdout)
    log_msg(f"Respaldo de cambios locales en conflicto guardado en: {patch_path}", verbose, log_file)
    return patch_path


def _merge_stashed_dirty_preferring_remote(
    repo_dir: str,
    remote_ref: str,
    dirty_entries: List[Dict[str, object]],
    local_ahead: int,
    backups_dir: str,
    verbose: bool,
    log_file: str,
) -> None:
    """
    Fusiona cambios remotos dando prioridad al remoto:
    1. Guarda en stash los cambios locales sin commit.
    2. Actualiza/fusiona desde remote_ref (-X theirs).
    3. Reaplica el stash; los cambios no solapados se fusionan y en caso de conflicto
       prevalece siempre el remoto (guardando respaldo .patch).
    """
    dirty_paths = [str(e["path"]) for e in dirty_entries]
    stashed = False
    if dirty_paths:
        stash_res = _run_cmd(
            ["git", "stash", "push", "-u", "-m", "auto-update-pre-merge", "--"] + dirty_paths,
            cwd=repo_dir,
        )
        if stash_res.returncode != 0:
            raise RuntimeError(f"git stash push falló: {stash_res.stderr.strip()}")
        stashed = "No local changes to save" not in stash_res.stdout

    if local_ahead > 0:
        _merge_remote(repo_dir, remote_ref, prefer="theirs", verbose=verbose, log_file=log_file)
    else:
        ff_res = _run_cmd(["git", "merge", "--ff-only", remote_ref], cwd=repo_dir)
        if ff_res.returncode != 0:
            _merge_remote(repo_dir, remote_ref, prefer="theirs", verbose=verbose, log_file=log_file)

    if stashed:
        pop_res = _run_cmd(["git", "stash", "pop"], cwd=repo_dir)
        if pop_res.returncode != 0:
            _save_stash_backup(repo_dir, backups_dir, verbose, log_file)
            # Durante stash pop, '--ours' corresponde a HEAD (remoto) y '--theirs' al stash (local)
            _resolve_unmerged_conflicts(repo_dir, prefer="ours", verbose=verbose, log_file=log_file)
            _run_cmd(["git", "reset", "HEAD"], cwd=repo_dir)
            _run_cmd(["git", "stash", "drop", "stash@{0}"], cwd=repo_dir)
            log_msg(
                "Conflicto al fusionar cambios locales antiguos con el remoto: prevaleció el remoto.",
                verbose,
                log_file,
            )


def _push_with_retry(
    repo_dir: str,
    remote: str,
    branch: str,
    verbose: bool,
    log_file: str,
) -> None:
    """Sube commits locales al remoto, reintentando una vez con merge -X ours si hubo push paralelo."""
    push_res = _run_cmd(["git", "push", remote, branch], cwd=repo_dir, timeout=90)
    if push_res.returncode == 0:
        return
    if fetch_remote(repo_dir, remote=remote, branch=branch, max_attempts=2, delay_sec=2.0, verbose=verbose, log_file=log_file):
        _merge_remote(repo_dir, f"{remote}/{branch}", prefer="ours", verbose=verbose, log_file=log_file)
        retry_res = _run_cmd(["git", "push", remote, branch], cwd=repo_dir, timeout=90)
        if retry_res.returncode == 0:
            return
        raise RuntimeError(f"git push falló tras reintento: {retry_res.stderr.strip()}")
    raise RuntimeError(f"git push falló: {push_res.stderr.strip()}")


def sync_repository(
    repo_dir: str,
    remote: str = "origin",
    branch: str = "main",
    dry_run: bool = False,
    verbose: bool = False,
    log_file: str = LOG_FILE,
    backups_dir: str = BACKUPS_DIR,
) -> Dict[str, object]:
    """
    Decide y ejecuta la estrategia de sincronización Git según las marcas temporales:
    - Sin cambios en ningún lado -> no-op.
    - Solo remoto nuevo -> pull fast-forward.
    - Cambios locales más recientes que remoto -> commit local, merge (-X ours) y push.
    - Cambios remotos más recientes o iguales -> merge dando prioridad al remoto (-X theirs).
    """
    state = inspect_repo_state(repo_dir, remote=remote, branch=branch)
    local_ahead = int(state["local_ahead"])
    remote_behind = int(state["remote_behind"])
    local_ts = float(state["local_ts"])
    remote_ts = float(state["remote_ts"])
    dirty_entries = list(state["dirty_entries"])
    has_local_changes = bool(dirty_entries) or local_ahead > 0

    if not has_local_changes and remote_behind == 0:
        log_msg("Repositorio al día (sin cambios locales ni remotos).", verbose, log_file)
        return {"action": "up_to_date", "changed": False, "state": state}

    remote_ref = f"{remote}/{branch}"

    if not has_local_changes and remote_behind > 0:
        log_msg(f"Hay {remote_behind} commit(s) nuevo(s) en {remote_ref}. Aplicando pull...", verbose, log_file)
        if dry_run:
            return {"action": "dry_run_pull", "changed": True, "state": state}
        res = _run_cmd(["git", "pull", "--ff-only", remote, branch], cwd=repo_dir)
        if res.returncode != 0:
            raise RuntimeError(f"git pull --ff-only falló: {res.stderr.strip()}")
        return {"action": "pulled_remote", "changed": True, "state": inspect_repo_state(repo_dir, remote, branch)}

    # En este punto existen cambios locales (dirty y/o commits sin subir)
    local_is_newer = local_ts > remote_ts

    if local_is_newer:
        log_msg(
            f"Cambios locales más recientes (local={datetime.fromtimestamp(local_ts).strftime('%Y-%m-%d %H:%M:%S')} "
            f"> remoto={datetime.fromtimestamp(remote_ts).strftime('%Y-%m-%d %H:%M:%S')}). "
            "Se fusionará priorizando local y se subirá al repositorio.",
            verbose,
            log_file,
        )
        if dry_run:
            return {"action": "dry_run_push_local", "changed": True, "state": state}
        if dirty_entries:
            _stage_and_commit_local(repo_dir, dirty_entries, verbose, log_file)
        if remote_behind > 0:
            _merge_remote(repo_dir, remote_ref, prefer="ours", verbose=verbose, log_file=log_file)
        _push_with_retry(repo_dir, remote=remote, branch=branch, verbose=verbose, log_file=log_file)
        return {"action": "pushed_local", "changed": True, "state": inspect_repo_state(repo_dir, remote, branch)}

    # Remoto es más reciente o igual
    if remote_behind == 0:
        log_msg(
            "No hay commits nuevos en remoto; cambios locales sin subir conservados sin cambios.",
            verbose,
            log_file,
        )
        return {"action": "local_kept_no_remote_updates", "changed": False, "state": state}

    log_msg(
        f"Cambios remotos más recientes o iguales (remoto={datetime.fromtimestamp(remote_ts).strftime('%Y-%m-%d %H:%M:%S')} "
        f">= local={datetime.fromtimestamp(local_ts).strftime('%Y-%m-%d %H:%M:%S')}). "
        "Fusionando dando prioridad al remoto...",
        verbose,
        log_file,
    )
    if dry_run:
        return {"action": "dry_run_merge_remote", "changed": True, "state": state}

    _merge_stashed_dirty_preferring_remote(
        repo_dir=repo_dir,
        remote_ref=remote_ref,
        dirty_entries=dirty_entries,
        local_ahead=local_ahead,
        backups_dir=backups_dir,
        verbose=verbose,
        log_file=log_file,
    )
    post_state = inspect_repo_state(repo_dir, remote, branch)
    if int(post_state["local_ahead"]) > 0:
        _push_with_retry(repo_dir, remote=remote, branch=branch, verbose=verbose, log_file=log_file)
        post_state = inspect_repo_state(repo_dir, remote, branch)
    return {"action": "merged_prefer_remote", "changed": True, "state": post_state}


def _file_sha256(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_sync_state(state_file: str = STATE_FILE) -> Dict[str, object]:
    try:
        if os.path.isfile(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_sync_state(data: Dict[str, object], state_file: str = STATE_FILE) -> None:
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_venv_python(repo_dir: str) -> str:
    venv_py = os.path.join(repo_dir, "venv", "Scripts", "python.exe")
    return venv_py if os.path.isfile(venv_py) else sys.executable


def get_venv_pythonw(repo_dir: str) -> str:
    venv_pyw = os.path.join(repo_dir, "venv", "Scripts", "pythonw.exe")
    if os.path.isfile(venv_pyw):
        return venv_pyw
    return get_venv_python(repo_dir)


def update_dependencies_if_needed(
    repo_dir: str,
    saved_state: Dict[str, object],
    repo_changed: bool,
    verbose: bool,
    log_file: str,
) -> str:
    """Instala dependencias si requirements.txt cambió respecto al estado sincronizado."""
    req_path = os.path.join(repo_dir, "requirements.txt")
    curr_hash = _file_sha256(req_path)
    prev_hash = str(saved_state.get("req_hash") or "")
    if curr_hash and prev_hash and curr_hash != prev_hash:
        log_msg("requirements.txt cambió: actualizando dependencias con pip...", verbose, log_file)
        py = get_venv_python(repo_dir)
        res = _run_cmd([py, "-m", "pip", "install", "-r", req_path], cwd=repo_dir, timeout=600)
        if res.returncode != 0:
            raise RuntimeError(f"pip install falló: {res.stderr.strip() or res.stdout.strip()}")
        log_msg("Dependencias actualizadas correctamente.", verbose, log_file)
    elif curr_hash and not prev_hash and repo_changed:
        # Si es la primera vez y el repo acaba de actualizarse, asegurar dependencias
        py = get_venv_python(repo_dir)
        _run_cmd([py, "-m", "pip", "install", "-r", req_path], cwd=repo_dir, timeout=600)
    return curr_hash


def restart_dev_watcher_if_running(repo_dir: str, verbose: bool, log_file: str) -> None:
    """Si gamepad_watcher.pyw de Lanzador estaba corriendo en segundo plano, lo reinicia tras actualizar."""
    try:
        import psutil
    except ImportError:
        return

    norm_watcher = os.path.normcase(os.path.join(repo_dir, "gamepad_watcher.pyw"))
    restarted = False
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name not in ("python.exe", "pythonw.exe"):
                continue
            cmd = proc.info.get("cmdline") or []
            if any(os.path.normcase(os.path.abspath(str(a))) == norm_watcher for a in cmd if str(a).lower().endswith("gamepad_watcher.pyw")):
                proc.terminate()
                restarted = True
        except Exception:
            continue

    if restarted:
        time.sleep(0.5)
        pyw = get_venv_pythonw(repo_dir)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([pyw, os.path.join(repo_dir, "gamepad_watcher.pyw")], cwd=repo_dir, creationflags=flags)
        log_msg("Watcher en segundo plano reiniciado con la nueva versión.", verbose, log_file)


def show_windows_toast(title: str, body: str) -> None:
    """Muestra una notificación discreta de Windows (no bloqueante) si es posible."""
    if os.name != "nt":
        return
    try:
        safe_title = title.replace("'", "''")
        safe_body = body.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f"$n.ShowBalloonTip(4500, '{safe_title}', '{safe_body}', [System.Windows.Forms.ToolTipIcon]::Info); "
            "Start-Sleep -Milliseconds 300; $n.Dispose()"
        )
        _run_cmd(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], cwd=BASE_DEV_DIR, timeout=8)
    except Exception:
        pass


def register_startup(repo_dir: str = BASE_DEV_DIR) -> str:
    """Registra GameFlowAutoUpdate en HKCU\\...\\Run para ejecutarse en cada inicio de sesión local."""
    import winreg

    pyw = get_venv_pythonw(repo_dir)
    script = os.path.join(repo_dir, "scripts", "auto_update.py")
    cmd = f'"{pyw}" "{script}"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH) as key:
        winreg.SetValueEx(key, STARTUP_VAL_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def unregister_startup() -> bool:
    """Elimina GameFlowAutoUpdate del registro de inicio de Windows."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, STARTUP_VAL_NAME)
        return True
    except FileNotFoundError:
        return False


def run_auto_update(
    repo_dir: str = BASE_DEV_DIR,
    player_dir: str = PLAYER_APP_DIR,
    dry_run: bool = False,
    force_build: bool = False,
    no_build: bool = False,
    no_notify: bool = False,
    max_fetch_attempts: int = 6,
    fetch_delay_sec: float = 5.0,
    verbose: bool = False,
) -> int:
    log_msg("=== Inicio de auto_update de GameFlow ===", verbose, LOG_FILE)
    saved_state = load_sync_state(STATE_FILE)

    if not fetch_remote(
        repo_dir,
        max_attempts=max_fetch_attempts,
        delay_sec=fetch_delay_sec,
        verbose=verbose,
        log_file=LOG_FILE,
    ):
        log_msg("Sin conexión con GitHub tras reintentos. Se omite la sincronización.", verbose, LOG_FILE)
        return 0

    try:
        sync_res = sync_repository(
            repo_dir=repo_dir,
            dry_run=dry_run,
            verbose=verbose,
            log_file=LOG_FILE,
            backups_dir=BACKUPS_DIR,
        )
    except Exception as exc:
        log_msg(f"ERROR durante la sincronización Git: {exc}", verbose, LOG_FILE)
        if not no_notify and not dry_run:
            show_windows_toast("GameFlow Auto-Update", f"Error en Git: {exc}")
        return 1

    if dry_run:
        log_msg(f"Dry-run completado: acción={sync_res['action']}", verbose, LOG_FILE)
        return 0

    post_state = sync_res["state"]
    curr_head = str(post_state["local_head"])
    curr_dirty_sig = str(post_state["dirty_sig"])
    repo_changed = bool(sync_res["changed"])

    try:
        req_hash = update_dependencies_if_needed(
            repo_dir, saved_state, repo_changed=repo_changed, verbose=verbose, log_file=LOG_FILE
        )
    except Exception as exc:
        log_msg(f"ERROR actualizando dependencias: {exc}", verbose, LOG_FILE)
        if not no_notify:
            show_windows_toast("GameFlow Auto-Update", f"Error instalando dependencias: {exc}")
        return 1

    player_exe = os.path.join(player_dir, "GameFlow Launcher.exe")
    needs_player_sync = (
        force_build
        or repo_changed
        or not os.path.isfile(player_exe)
        or saved_state.get("synced_commit") != curr_head
        or saved_state.get("synced_dirty_sig") != curr_dirty_sig
    )

    if not no_build and needs_player_sync:
        log_msg("Actualizando aplicación particular (compilando y sincronizando GameFlow)...", verbose, LOG_FILE)
        py = get_venv_python(repo_dir)
        sync_script = os.path.join(repo_dir, "scripts", "sync_to_player.py")
        sync_proc = _run_cmd([py, sync_script], cwd=repo_dir, timeout=900)
        if sync_proc.returncode != 0:
            err_detail = (sync_proc.stderr or sync_proc.stdout).strip()[-400:]
            log_msg(f"ERROR en sync_to_player.py (código {sync_proc.returncode}): {err_detail}", verbose, LOG_FILE)
            if not no_notify:
                show_windows_toast("GameFlow Auto-Update", "Falló la compilación/actualización de GameFlow.")
            return 1
        log_msg("Aplicación particular GameFlow actualizada con éxito.", verbose, LOG_FILE)
        if repo_changed:
            restart_dev_watcher_if_running(repo_dir, verbose, LOG_FILE)
        if not no_notify:
            show_windows_toast(
                "GameFlow actualizado",
                f"Proyecto y app personal sincronizados ({sync_res['action']}).",
            )
    else:
        log_msg("La aplicación particular GameFlow ya está actualizada para este commit.", verbose, LOG_FILE)

    save_sync_state(
        {
            "synced_commit": curr_head,
            "synced_dirty_sig": curr_dirty_sig,
            "req_hash": req_hash,
            "last_action": sync_res["action"],
            "last_sync_iso": datetime.now().isoformat(timespec="seconds"),
        },
        state_file=STATE_FILE,
    )
    log_msg("=== Fin de auto_update de GameFlow ===", verbose, LOG_FILE)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-actualizador de GameFlow al iniciar sesión.")
    parser.add_argument("--dry-run", action="store_true", help="Muestra la acción que tomaría sin modificar nada.")
    parser.add_argument("--force-build", action="store_true", help="Recompila y actualiza GameFlow aunque no haya commits nuevos.")
    parser.add_argument("--no-build", action="store_true", help="Solo sincroniza Git sin compilar la app particular.")
    parser.add_argument("--no-notify", action="store_true", help="No mostrar notificación de Windows.")
    parser.add_argument("--no-lock", action="store_true", help="No adquirir mutex de instancia única.")
    parser.add_argument("--verbose", action="store_true", help="Imprime los logs por consola.")
    parser.add_argument("--register-startup", action="store_true", help="Registra el script en el inicio de Windows.")
    parser.add_argument("--unregister-startup", action="store_true", help="Elimina el script del inicio de Windows.")
    args = parser.parse_args()

    if args.register_startup:
        cmd = register_startup(BASE_DEV_DIR)
        print(f"[OK] Registrado en inicio de Windows ({STARTUP_VAL_NAME}): {cmd}")
        return 0
    if args.unregister_startup:
        removed = unregister_startup()
        print("[OK] Eliminado del inicio de Windows." if removed else "[INFO] No estaba registrado.")
        return 0

    _mutex = None
    if not args.no_lock:
        _mutex = acquire_single_instance_mutex()
        if _mutex is False:
            log_msg("Ya hay una instancia de auto_update en ejecución; saliendo.", args.verbose, LOG_FILE)
            return 0

    return run_auto_update(
        dry_run=args.dry_run,
        force_build=args.force_build,
        no_build=args.no_build,
        no_notify=args.no_notify,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
