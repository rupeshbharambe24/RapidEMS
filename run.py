#!/usr/bin/env python3
"""
=================================================================
 AI Emergency Response System — One-command launcher
=================================================================

Usage:
    python run.py                  # full setup + start backend + simulator + frontend
    python run.py --no-sim         # backend + frontend only
    python run.py --no-frontend    # backend + simulator only
    python run.py --backend-only   # just the backend
    python run.py --setup-only     # set up env / db / models, then exit
    python run.py --skip-install   # skip pip + npm install (faster restart)
    python run.py --reset-db       # delete the SQLite db before starting

Phases:
    1. Check Python version (>= 3.10)
    2. Create / reuse .venv
    3. pip install -r backend/requirements.txt  (skipped if cached)
    4. Initialise database (auto-create tables)
    5. Detect ML models — offer quick_train if any are missing
    6. Check Node + npm install for the frontend (skipped if cached)
    7. Spawn backend (uvicorn) + simulator + frontend (vite) subprocesses
    8. Stream their logs; Ctrl-C cleanly stops everything
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
SIM = ROOT / "simulator"
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
REQS = BACKEND / "requirements.txt"
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
PIP_STAMP = VENV / ".reqs-installed-on"
NPM_STAMP = FRONTEND / "node_modules" / ".package-installed-on"
MODELS_DIR = BACKEND / "ai_models"

# Cross-platform venv binary paths
IS_WINDOWS = platform.system() == "Windows"
PY_BIN = VENV / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")
PIP_BIN = VENV / ("Scripts" if IS_WINDOWS else "bin") / ("pip.exe" if IS_WINDOWS else "pip")

REQUIRED_MODEL_FILES = [
    "severity_classifier.pkl", "severity_scaler.pkl", "severity_feature_cols.pkl",
    "eta_xgb.pkl", "eta_scaler.pkl", "eta_feature_cols.pkl",
    "hospital_recommender.pkl", "hospital_scaler.pkl", "hospital_feature_cols.pkl",
    "traffic_predictor.pkl", "traffic_scaler.pkl", "traffic_feature_cols.pkl",
    "hotspot_lstm.keras", "hotspot_count_scaler.pkl",
]


# ────────────────────── pretty print helpers ──────────────────────
class C:
    G  = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[94m"
    BOLD = "\033[1m"; END = "\033[0m"

def step(n, total, msg): print(f"\n{C.B}[{n}/{total}]{C.END} {C.BOLD}{msg}{C.END}")
def ok(msg):   print(f"   {C.G}✓{C.END} {msg}")
def warn(msg): print(f"   {C.Y}⚠{C.END} {msg}")
def fail(msg): print(f"   {C.R}✗{C.END} {msg}")
def info(msg): print(f"   {msg}")


def banner():
    print(C.BOLD + "=" * 64)
    print(" 🚑  AI Emergency Response System — bootstrapping")
    print("=" * 64 + C.END)


# ────────────────────── phases ──────────────────────
def phase_python(total):
    step(1, total, "Checking Python version...")
    v = sys.version_info
    if (v.major, v.minor) < (3, 10):
        fail(f"Python 3.10+ required (found {v.major}.{v.minor}.{v.micro}).")
        info("Install from https://www.python.org/downloads/ and re-run this script.")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def phase_env(total):
    step(2, total, "Preparing environment file...")
    if not ENV_FILE.exists():
        if ENV_EXAMPLE.exists():
            shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
            ok(f"Created .env from .env.example")
        else:
            warn("No .env or .env.example found; using built-in defaults.")
    else:
        ok(".env present")


def phase_venv(total):
    step(3, total, "Setting up virtual environment...")
    if VENV.exists() and PY_BIN.exists():
        ok(f"venv already exists at {VENV}")
        return
    info("creating .venv ...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    ok(f"venv created at {VENV}")


def phase_install(total, skip: bool):
    step(4, total, "Installing backend dependencies...")
    if skip:
        warn("--skip-install given; skipping pip install.")
        return
    needs_install = True
    if PIP_STAMP.exists():
        try:
            stamp_t = PIP_STAMP.stat().st_mtime
            reqs_t = REQS.stat().st_mtime
            if stamp_t >= reqs_t:
                needs_install = False
        except Exception:
            pass
    if not needs_install:
        ok("dependencies already up to date")
        return
    info("running pip install (TensorFlow alone is ~600MB; first run can take several minutes) ...")
    subprocess.run(
        [str(PY_BIN), "-m", "pip", "install", "--upgrade", "pip"], check=True,
    )
    res = subprocess.run(
        [str(PY_BIN), "-m", "pip", "install", "-r", str(REQS)],
        check=False,
    )
    if res.returncode != 0:
        fail("pip install failed.")
        info("Try running manually:")
        info(f"   {PIP_BIN} install -r {REQS}")
        sys.exit(1)
    PIP_STAMP.write_text(str(time.time()))
    ok("dependencies installed")


def phase_db(total, reset: bool):
    step(5, total, "Initialising database...")
    db_file = BACKEND / "emergency.db"
    if reset and db_file.exists():
        db_file.unlink()
        warn(f"deleted existing {db_file.name}")
    # Run a tiny in-process check to call create_all_tables + seed
    code = (
        "import sys; sys.path.insert(0, '.');"
        "from app.database import create_all_tables; create_all_tables();"
        "from app.database import SessionLocal; from app.seed import seed_database;"
        "db = SessionLocal(); seed_database(db); db.close();"
        "print('   db ready')"
    )
    res = subprocess.run([str(PY_BIN), "-c", code], cwd=str(BACKEND))
    if res.returncode != 0:
        fail("DB initialisation failed.")
        sys.exit(1)
    ok("database tables + seed data ready")


def models_status():
    present, missing = [], []
    for f in REQUIRED_MODEL_FILES:
        p = MODELS_DIR / f
        (present if p.exists() and p.stat().st_size > 0 else missing).append(f)
    return present, missing


def phase_models(total, non_interactive: bool):
    step(6, total, "Detecting trained ML models...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    present, missing = models_status()
    info(f"{len(present)}/{len(REQUIRED_MODEL_FILES)} model files found in {MODELS_DIR}")
    if not missing:
        ok("all 5 models present")
        return
    warn("some model files are missing — without them, heuristic fallbacks will be used.")
    print("\n   Choices:")
    print("     [A] Run notebooks 1-5 manually for full quality (~30 min total)")
    print("     [B] Run quick_train.py now (lightweight models, ~90s)  ← recommended for first run")
    print("     [C] Skip — backend will run but use heuristic fallbacks for missing models")

    if non_interactive:
        choice = "C"
        info("(non-interactive mode → choosing C)")
    else:
        try:
            choice = input("   Choose [A/B/C] (default C): ").strip().upper() or "C"
        except (EOFError, KeyboardInterrupt):
            choice = "C"

    if choice == "A":
        info("Open notebooks/01_severity_classifier.ipynb (and 02-05) in Jupyter and run all cells.")
        info("Each notebook saves its artifacts directly to backend/ai_models/.")
        info("Re-run this script when done.")
    elif choice == "B":
        info("Training lightweight models — this takes ~90s ...")
        res = subprocess.run(
            [str(PY_BIN), "-m", "app.ai.quick_train"],
            cwd=str(BACKEND),
        )
        if res.returncode == 0:
            present2, missing2 = models_status()
            ok(f"quick-train done ({len(present2)}/{len(REQUIRED_MODEL_FILES)} models present)")
        else:
            warn("quick-train failed; backend will fall back to heuristics for those models.")
    else:
        warn("skipping model training — heuristic fallbacks will be used.")


def phase_frontend(total, skip_install: bool, no_frontend: bool):
    step(7, total, "Setting up frontend...")
    if no_frontend:
        info("--no-frontend given; skipping.")
        return False
    if not FRONTEND.exists():
        warn("frontend/ directory not found; skipping.")
        return False
    # Check Node
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        warn("Node.js / npm not found in PATH.")
        info("Install Node 18+ from https://nodejs.org/ — backend + simulator will still run.")
        return False
    try:
        ver = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
        ok(f"Node {ver}")
    except Exception:
        warn("Node version check failed; skipping frontend.")
        return False

    # npm install if needed
    pkg_json = FRONTEND / "package.json"
    if skip_install:
        warn("--skip-install: skipping npm install")
    else:
        needs = True
        if NPM_STAMP.exists():
            try:
                if NPM_STAMP.stat().st_mtime >= pkg_json.stat().st_mtime:
                    needs = False
            except Exception:
                pass
        if needs:
            info("running npm install (first run takes ~60s)...")
            res = subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund"],
                                 cwd=str(FRONTEND))
            if res.returncode != 0:
                fail("npm install failed; the frontend will not start.")
                info("Try manually: cd frontend && npm install")
                return False
            NPM_STAMP.parent.mkdir(parents=True, exist_ok=True)
            NPM_STAMP.write_text(str(time.time()))
            ok("frontend dependencies installed")
        else:
            ok("frontend dependencies up to date")
    return True


def phase_run(total, no_sim: bool, port: int, frontend_ready: bool):
    step(8, total, "Starting services...")
    print()
    print(C.G + "  Backend:    " + C.END + f"http://localhost:{port}    (API docs: /docs)")
    if not no_sim:
        print(C.G + "  Simulator:  " + C.END + "ambulance fleet active (~20 units)")
    if frontend_ready:
        print(C.G + "  Frontend:   " + C.END + "http://localhost:5173    (login: admin / admin123)")
    print(C.G + "  Health:     " + C.END + f"http://localhost:{port}/health")
    print()
    print(C.Y + "  Press Ctrl-C to stop everything." + C.END)
    print()

    backend_proc = subprocess.Popen(
        [str(PY_BIN), "-m", "uvicorn", "app.main:asgi",
         "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(BACKEND),
    )
    sim_proc = None
    if not no_sim:
        time.sleep(3)   # let backend bind first
        sim_proc = subprocess.Popen(
            [str(PY_BIN), str(SIM / "gps_simulator.py"),
             "--backend", f"http://localhost:{port}"],
        )
    frontend_proc = None
    if frontend_ready:
        npm = shutil.which("npm")
        # Vite uses unicode for its banner — disable that on Windows quirks
        env = os.environ.copy()
        env["BROWSER"] = "none"        # prevent Vite auto-opening
        frontend_proc = subprocess.Popen(
            [npm, "run", "dev", "--", "--host"],
            cwd=str(FRONTEND), env=env,
        )

    procs = [p for p in (backend_proc, sim_proc, frontend_proc) if p is not None]

    def shutdown(*_):
        print("\n" + C.Y + "Stopping..." + C.END)
        for p in procs:
            try: p.terminate()
            except Exception: pass
        for p in procs:
            try: p.wait(timeout=8)
            except Exception:
                try: p.kill()
                except Exception: pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for p in procs:
                rc = p.poll()
                if rc is not None:
                    fail(f"a child process exited with code {rc}; shutting down.")
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


# ────────────────────── main ──────────────────────
def main():
    parser = argparse.ArgumentParser(description="AI Emergency Response launcher")
    parser.add_argument("--no-sim", action="store_true",
                        help="don't start the GPS simulator")
    parser.add_argument("--no-frontend", action="store_true",
                        help="don't build/start the frontend")
    parser.add_argument("--backend-only", action="store_true",
                        help="alias for --no-sim --no-frontend")
    parser.add_argument("--setup-only", action="store_true",
                        help="set up environment + db + models, then exit")
    parser.add_argument("--skip-install", action="store_true",
                        help="skip pip + npm install (faster on subsequent runs)")
    parser.add_argument("--reset-db", action="store_true",
                        help="delete the SQLite database before starting")
    parser.add_argument("--port", type=int, default=8000,
                        help="backend port (default 8000)")
    parser.add_argument("--non-interactive", action="store_true",
                        help="don't prompt for missing-model choice (default to skip)")
    args = parser.parse_args()

    if args.backend_only:
        args.no_sim = True
        args.no_frontend = True

    banner()
    total = 8
    phase_python(total)
    phase_env(total)
    phase_venv(total)
    phase_install(total, args.skip_install)
    phase_db(total, args.reset_db)
    phase_models(total, args.non_interactive)
    frontend_ready = phase_frontend(total, args.skip_install, args.no_frontend)
    if args.setup_only:
        print("\n" + C.G + "✓ Setup complete." + C.END)
        return
    phase_run(total, args.no_sim, args.port, frontend_ready)


if __name__ == "__main__":
    main()
