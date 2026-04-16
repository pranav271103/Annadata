"""
Annadata OS — Unified Orchestrator (Universal)
==============================================
Starts all 12 backend microservices + the Next.js frontend in a single terminal.
Enables 'Zero-Install' (SQLite) mode by default for local development.

Usage:
    python orchestrator.py          # Start everything
    python orchestrator.py --backend-only   # Skip frontend
    python orchestrator.py --service [name] # Start only one service
    python orchestrator.py --postgres       # Force Postgres mode
"""

import subprocess
import sys
import os
import signal
import time
import threading
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Service registry — maps service name → (module path, port)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

SERVICES = [
    ("msp_mitra",           "services.msp_mitra.app:app",           8001),
    ("soilscan_ai",         "services.soilscan_ai.app:app",         8002),
    ("fasal_rakshak",       "services.fasal_rakshak.app:app",       8003),
    ("jal_shakti",          "services.jal_shakti.app:app",           8004),
    ("harvest_shakti",      "services.harvest_shakti.app:app",       8005),
    ("kisaan_sahayak",      "services.kisaan_sahayak.app:app",       8006),
    ("protein_engineering", "services.protein_engineering.app:app",   8007),
    ("kisan_credit",        "services.kisan_credit.app:app",         8008),
    ("harvest_to_cart",     "services.harvest_to_cart.app:app",       8009),
    ("beej_suraksha",       "services.beej_suraksha.app:app",        8010),
    ("mausam_chakra",       "services.mausam_chakra.app:app",        8011),
    ("gamification",        "services.gamification.app:app",          8012),
]

# Windows-compatible ANSI colours
COLORS = [
    "\033[92m",  # green
    "\033[93m",  # yellow
    "\033[94m",  # blue
    "\033[95m",  # magenta
    "\033[96m",  # cyan
    "\033[91m",  # red
    "\033[97m",  # white
    "\033[33m",  # dark yellow
    "\033[36m",  # dark cyan
    "\033[35m",  # dark magenta
    "\033[32m",  # dark green
    "\033[34m",  # dark blue
    "\033[37m",  # light grey
]
RESET = "\033[0m"

processes = []
shutdown_event = threading.Event()


def stream_output(proc, label, color):
    """Read lines from a subprocess and print them with a label prefix."""
    for line in iter(proc.stdout.readline, b""):
        if shutdown_event.is_set():
            break
        try:
            text = line.decode("utf-8", errors="replace").rstrip()
            print(f"{color}[{label:>20}]{RESET} {text}")
        except (UnicodeEncodeError, Exception):
            # Fallback for Windows console or other transport errors
            try:
                text = line.decode("utf-8", errors="replace").rstrip()
                msg = text.encode("ascii", "replace").decode("ascii")
                print(f"{color}[{label:>20}]{RESET} {msg}")
            except Exception:
                pass
    proc.stdout.close()


def start_backend_service(name, module, port, color, use_sqlite=True):
    """Start a single uvicorn backend service."""
    python = sys.executable
    cmd = [
        python, "-m", "uvicorn",
        module,
        "--host", "0.0.0.0",
        "--port", str(port),
        "--reload",
        "--log-level", "info",
    ]
    
    env = {
        **os.environ, 
        "PYTHONPATH": str(ROOT),
        "USE_SQLITE": "True" if use_sqlite else "False"
    }
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    t = threading.Thread(target=stream_output, args=(proc, name, color), daemon=True)
    t.start()
    return proc


def start_frontend(color):
    """Start the Next.js frontend dev server."""
    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "node_modules").exists():
        print(f"{color}[{'frontend':>20}]{RESET} Installing npm dependencies...")
        subprocess.run(
            ["npm", "install"],
            cwd=str(frontend_dir),
            shell=True,
            check=True,
        )

    cmd = ["npm", "run", "dev"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(frontend_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={**os.environ, "NEXT_PUBLIC_API_BASE_URL": "http://localhost:3000"},
        shell=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    t = threading.Thread(target=stream_output, args=(proc, "frontend", color), daemon=True)
    t.start()
    return proc


def shutdown(signum=None, frame=None):
    """Gracefully terminate all child processes."""
    shutdown_event.set()
    print(f"\n{COLORS[5]}[{'orchestrator':>20}]{RESET} Shutting down all services...")
    for proc in processes:
        try:
            if os.name == "nt":
                proc.terminate()
            else:
                proc.send_signal(signal.SIGTERM)
        except Exception:
            pass
    # Wait briefly for graceful shutdown
    for proc in processes:
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print(f"{COLORS[5]}[{'orchestrator':>20}]{RESET} All services stopped.")
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Annadata OS Orchestrator (Universal)")
    parser.add_argument("--backend-only", action="store_true", help="Skip frontend")
    parser.add_argument("--service", type=str, help="Start only a specific service")
    parser.add_argument("--postgres", action="store_true", help="Force PostgreSQL mode (requires Docker)")
    args = parser.parse_args()

    # Enable ANSI on Windows
    if os.name == "nt":
        os.system("color")

    signal.signal(signal.SIGINT, shutdown)
    if os.name != "nt":
        signal.signal(signal.SIGTERM, shutdown)

    use_sqlite = not args.postgres

    print("=" * 60)
    print("  ANNADATA OS — Unified Orchestrator")
    mode_str = "Zero-Install (SQLite)" if use_sqlite else "Standard (Postgres/Redis)"
    print(f"  Mode: {mode_str}")
    print("=" * 60)

    services_to_start = SERVICES
    if args.service:
        services_to_start = [(n, m, p) for n, m, p in SERVICES if n == args.service]
        if not services_to_start:
            print(f"Error: Service '{args.service}' not found.")
            print(f"Available: {', '.join(n for n, _, _ in SERVICES)}")
            sys.exit(1)

    # Start backend services
    for i, (name, module, port) in enumerate(services_to_start):
        color = COLORS[i % len(COLORS)]
        print(f"{color}[{'orchestrator':>20}]{RESET} Starting {name} on port {port}...")
        proc = start_backend_service(name, module, port, color, use_sqlite=use_sqlite)
        processes.append(proc)
        time.sleep(0.3)  # Stagger startup to reduce load

    # Start frontend
    if not args.backend_only and not args.service:
        color = COLORS[len(services_to_start) % len(COLORS)]
        print(f"{color}[{'orchestrator':>20}]{RESET} Starting frontend on port 3000...")
        proc = start_frontend(color)
        processes.append(proc)

    print()
    print("=" * 60)
    if not args.service:
        print("  All services started!")
        print(f"  Dashboard:  http://localhost:3000/dashboard")
        print(f"  Game:       http://localhost:3000/game")
        print(f"  API Docs:   http://localhost:8001/docs")
    else:
        name, _, port = services_to_start[0]
        print(f"  {name} started on port {port}")
    print("  Press Ctrl+C to stop all services")
    print("=" * 60)

    # Keep main thread alive
    try:
        while not shutdown_event.is_set():
            for proc in processes:
                if proc.poll() is not None:
                    pass
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
