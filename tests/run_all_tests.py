"""
Ejecutor unificado de todas las suites de prueba de GameFlow Launcher.
Ejecuta cada suite en un subproceso aislado para garantizar que los contextos Tcl/Tk
de diferentes pruebas gráficas no colisionen entre sí, seguido de la Mega Auditoría.
"""
import glob
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    test_files = sorted(glob.glob(os.path.join(tests_dir, "test_*.py")))
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["GAMEFLOW_DISABLE_WATCHER"] = "1"

    passed = 0
    failed = []
    t_start = time.time()

    print(f"Ejecutando {len(test_files)} suites en {os.path.relpath(tests_dir, BASE_DIR)}/ ...")
    for test_path in test_files:
        rel = os.path.relpath(test_path, BASE_DIR)
        t0 = time.time()
        try:
            res = subprocess.run(
                [sys.executable, "-m", "unittest", test_path],
                cwd=BASE_DIR,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            dt = time.time() - t0
            if res.returncode == 0:
                passed += 1
                print(f"  [PASS] {rel} ({dt:.2f}s)")
            else:
                failed.append((rel, res.returncode, (res.stdout + "\n" + res.stderr).strip()))
                print(f"  [FAIL] {rel} (rc={res.returncode}, {dt:.2f}s)")
        except subprocess.TimeoutExpired as exc:
            dt = time.time() - t0
            out = (exc.stdout or "") + "\n" + (exc.stderr or "")
            failed.append((rel, "TIMEOUT", out.strip() or f"Timeout after {exc.timeout}s"))
            print(f"  [FAIL] {rel} (TIMEOUT, {dt:.2f}s)")

    audit_script = os.path.join(tests_dir, "mega_audit_test_suite.py")
    print("\nEjecutando Mega Auditoria...")
    try:
        audit_res = subprocess.run(
            [sys.executable, audit_script],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if audit_res.returncode == 0:
            print("  [PASS] tests/mega_audit_test_suite.py")
        else:
            failed.append(("tests/mega_audit_test_suite.py", audit_res.returncode, (audit_res.stdout + "\n" + audit_res.stderr).strip()))
            print(f"  [FAIL] tests/mega_audit_test_suite.py (rc={audit_res.returncode})")
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + "\n" + (exc.stderr or "")
        failed.append(("tests/mega_audit_test_suite.py", "TIMEOUT", out.strip() or f"Timeout after {exc.timeout}s"))
        print("  [FAIL] tests/mega_audit_test_suite.py (TIMEOUT)")

    elapsed = time.time() - t_start
    print(f"\nResumen: {passed}/{len(test_files)} suites + Mega Auditoria | Fallos: {len(failed)} | Tiempo: {elapsed:.1f}s")

    if failed:
        for rel, rc, output in failed:
            print(f"\n=== {rel} (rc={rc}) ===")
            print(output[-1200:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
