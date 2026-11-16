# Instrucciones del Proyecto — GameFlow Launcher

Antes de explorar el código o realizar cambios, lee [`WALKTHROUGH.md`](WALKTHROUGH.md) para consultar la arquitectura, invariantes técnicas y el historial de cambios.

---

## Flujo Obligatorio de Entrega e Iteración (Empaquetado Local → Confirmación → Git)

Al finalizar **cualquier cambio** de código, UI, configuración o empaquetado:

1. **Verificación de pruebas (`tests/`):**
   - Ejecuta la suite completa y verifica **0 fallos**:
     ```powershell
     .\venv\Scripts\python.exe tests\run_all_tests.py
     ```
2. **Empaquetado y sincronización local OBLIGATORIA para pruebas del usuario:**
   - El usuario prueba los cambios directamente sobre el ejecutable compilado en `C:\Users\jorge\Documents\Programas\GameFlow`.
   - Tras pasar los tests, ejecuta siempre:
     ```powershell
     .\venv\Scripts\python.exe scripts\sync_to_player.py
     ```
   - Esto compila con PyInstaller (`build.py`) y actualiza `C:\Users\jorge\Documents\Programas\GameFlow\GameFlow Launcher.exe` preservando intactos `games.json`, `covers/`, `wallpapers/` y configuraciones personales.
3. **PROHIBIDO subir a Git automáticamente:**
   - **NO** ejecutes `git commit`, `git push` ni `scripts/auto_update.py` por iniciativa propia tras un cambio.
   - Una vez empaquetada la versión local, informa de lo realizado y **pregunta explícitamente al usuario** si quiere iterar algún ajuste adicional o si el cambio está listo para actualizar el repositorio (local + remoto).
4. **Cierre y subida al repositorio (SOLO tras confirmación explícita del usuario):**
   - Verifica la seguridad de archivos staged antes de commitear (exit `0` obligatorio):
     ```powershell
     .\venv\Scripts\python.exe scripts\verify_clean_git.py
     ```
   - Actualiza [`WALKTHROUGH.md`](WALKTHROUGH.md) (sección afectada + entrada cronológica inversa en la Sección 8) si corresponde.
   - Realiza `git commit` y `git push origin main`.

---

## Reglas Técnicas Críticas

- **Privacidad Git:** Nunca incluyas en commits `games.json`, `games.json.bak`, `gamepad_config.json`, `collections_config.json`, `emulators_config.json`, `game_stats.json`, `achievements_*.json`, `cloud_sync.json`, `covers/*` (salvo `.gitkeep`), `wallpapers/*` (salvo `.gitkeep`), `save_backups/`, `.cache/`, `*.log`, `*.bak`, `*.lnk` ni `.portable`.
- **Compatibilidad:** Respeta siempre soporte multi-monitor con distintos DPI en Windows, modo empaquetado PyInstaller (`sys.frozen` / `_internal/`), modo portable (`.portable`) y compatibilidad CI/tests en Linux (`core/platform_layer.py`).
- **Módulos nuevos:** Regístralos en `gameflow.spec` (`launcher_hiddenimports` / `watcher_hiddenimports` / `sentinel_hiddenimports`) y en `files_to_check` dentro de `tests/mega_audit_test_suite.py`.
- **Modales y Tkinter:** Tkinter/CTk no es thread-safe (`_action_queue` / `after(0, ...)` con comprobación `winfo_exists()`). Todo modal nuevo debe heredar de `BaseGlassDialog` o registrarse en `modal_manager`, ocultar de barra de tareas (`hide_from_taskbar()` siempre **después** de `attributes("-alpha", ...)`), e implementar `handle_gamepad_input`.
