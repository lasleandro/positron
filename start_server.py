#!/usr/bin/env python3
"""
Positron (Meus Exames) - unified launcher
==========================================

Development (default): Django API + Vite dev server with hot reload.
    python start_server.py
        App      -> http://localhost:$FRONTEND_PORT  (Vite, proxies /api to Django)
        API      -> http://localhost:$BACKEND_PORT/api/

Production-like: build the React bundle and let Django serve everything from one
port, with the real CSP headers applied to the page.
    python start_server.py --build
        App      -> http://localhost:$BACKEND_PORT

Both modes apply pending migrations first and run the email worker (invitations,
password reset). Configuration comes from .env.
"""

import argparse
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import threading
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
CONDA_PYTHON = Path.home() / "anaconda3" / "envs" / "positron" / "bin" / "python"
PYTHON_BIN = Path(os.getenv("POSITRON_PYTHON", CONDA_PYTHON if CONDA_PYTHON.exists() else sys.executable))

try:
    from dotenv import load_dotenv
except ImportError:
    # Launched with an interpreter outside the positron env: re-run inside it.
    if Path(sys.executable).resolve() != PYTHON_BIN.resolve() and PYTHON_BIN.exists():
        os.execv(str(PYTHON_BIN), [str(PYTHON_BIN), __file__, *sys.argv[1:]])
    sys.exit("python-dotenv missing. Run: conda activate positron && pip install -r requirements.txt")

load_dotenv(ROOT / ".env")
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8030"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5190"))

_processes: list[subprocess.Popen] = []


def find_npm() -> str | None:
    """npm may live only under nvm, which conda activation can push off PATH."""
    npm = shutil.which("npm")
    if npm:
        return npm
    candidates = sorted(glob(str(Path.home() / ".nvm/versions/node/*/bin/npm")))
    return candidates[-1] if candidates else None


def npm_env(npm: str) -> dict:
    env = os.environ.copy()
    env["PATH"] = f"{Path(npm).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def fail(message: str) -> None:
    print(f"  ERROR: {message}")
    sys.exit(1)


def run_step(label: str, args: list[str], **kwargs) -> None:
    """Run a blocking setup step; abort the launcher if it fails."""
    print(f"  {label} ...")
    if subprocess.run(args, **kwargs).returncode != 0:
        fail(f"{label} failed.")


def popen(args: list[str], **kwargs) -> subprocess.Popen:
    """Each child leads its own process group so Ctrl+C reaches grandchildren
    (runserver's autoreloader, Vite under npm) and nothing is left running."""
    proc = subprocess.Popen(
        args, start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, **kwargs,
    )
    _processes.append(proc)
    return proc


def stop_all(*_) -> None:
    print("\n  Stopping servers ...")
    for proc in _processes:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    for proc in _processes:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    print("  All servers stopped.")
    sys.exit(0)


def stream(label: str, proc: subprocess.Popen, out: "queue.Queue[tuple[str, str | None]]") -> None:
    for line in proc.stdout:
        out.put((label, line.rstrip()))
    out.put((label, None))


def prepare(npm: str, build: bool, backend_env: dict) -> None:
    if not PYTHON_BIN.exists():
        fail(f"Python not found at {PYTHON_BIN}. Create it: conda create -n positron python=3.11")
    if not (FRONTEND_DIR / "node_modules").exists():
        run_step("Installing frontend dependencies", [npm, "ci"], cwd=FRONTEND_DIR, env=npm_env(npm))
    run_step("Applying migrations", [str(PYTHON_BIN), "manage.py", "migrate", "--noinput"], cwd=ROOT, env=backend_env)
    if build:
        run_step("Building frontend bundle", [npm, "run", "build"], cwd=FRONTEND_DIR, env=npm_env(npm))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Positron backend and frontend together.")
    parser.add_argument("--build", action="store_true", help="build the SPA and serve it from Django (single port)")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    npm = find_npm()
    if not npm:
        fail("npm not found (checked PATH and ~/.nvm).")
    ports = [BACKEND_PORT] if args.build else [BACKEND_PORT, FRONTEND_PORT]
    busy = [port for port in ports if port_in_use(port)]
    if busy:
        fail(f"port(s) {busy} already in use. Stop that process or change BACKEND_PORT/FRONTEND_PORT in .env.")

    backend_env = os.environ.copy()
    backend_env["PYTHONUNBUFFERED"] = "1"  # stream Django/worker logs (console email links) live
    if args.build:
        # The page is served by Django itself, so QR and invite links must point there.
        backend_env["APP_ORIGIN"] = f"http://localhost:{BACKEND_PORT}"

    print("=" * 72)
    print("  Positron - Meus Exames")
    print("=" * 72)
    print(f"  Python:   {PYTHON_BIN}")
    prepare(npm, args.build, backend_env)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)
    active = [("backend", popen(
        [str(PYTHON_BIN), "manage.py", "runserver", f"{BACKEND_HOST}:{BACKEND_PORT}"], cwd=ROOT, env=backend_env,
    ))]
    active.append(("mailer", popen([str(PYTHON_BIN), "manage.py", "send_emails"], cwd=ROOT, env=backend_env)))
    if not args.build:
        active.append(("frontend", popen([npm, "run", "dev"], cwd=FRONTEND_DIR, env=npm_env(npm))))

    print()
    app_port = BACKEND_PORT if args.build else FRONTEND_PORT
    print(f"  App      -> http://localhost:{app_port}")
    print(f"  API      -> http://localhost:{BACKEND_PORT}/api/session/")
    print("  Press Ctrl+C to stop.")
    print("=" * 72)

    output: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
    for label, proc in active:
        threading.Thread(target=stream, args=(label, proc, output), daemon=True).start()
    while True:
        label, line = output.get()
        if line is None:
            proc = dict(active)[label]
            print(f"  [{label}] exited with code {proc.wait()}")
            stop_all()
        print(f"  [{label}] {line}")


if __name__ == "__main__":
    main()
