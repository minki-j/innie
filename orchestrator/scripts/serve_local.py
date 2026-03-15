"""
Starts a local Prefect server and serves the video_pipeline flow.
Usage: uv run serve-local
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


PREFECT_API_URL = "http://127.0.0.1:4200/api"
ORCHESTRATOR_DIR = Path(__file__).parent.parent


def wait_for_server(timeout: int = 30) -> None:
    print("Waiting for Prefect server to be ready...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{PREFECT_API_URL}/health", timeout=1)
            print("Server is ready.")
            return
        except Exception:
            time.sleep(1)
    print("Timed out waiting for Prefect server.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    os.environ["PREFECT_API_URL"] = PREFECT_API_URL
    # SQLite gets "database is locked" when concurrent writes race. Raising the
    # acquire timeout gives queued writers enough time to succeed instead of
    # failing immediately.
    os.environ.setdefault("PREFECT_API_DATABASE_TIMEOUT", "60")
    os.environ.setdefault("PREFECT_API_DATABASE_CONNECTION_TIMEOUT", "60")

    procs: list[subprocess.Popen] = []

    def shutdown(signum=None, frame=None):
        print("\nShutting down...")
        for p in procs:
            p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Starting Prefect server...")
    server_proc = subprocess.Popen(
        ["uv", "run", "prefect", "server", "start"],
        cwd=ORCHESTRATOR_DIR,
    )
    procs.append(server_proc)

    wait_for_server()

    print("Serving video_pipeline flow...")
    flow_proc = subprocess.Popen(
        [
            "uv", "run", "prefect", "flow", "serve",
            "flows/video_pipeline.py:video_pipeline",
            "--name", "video-pipeline",
        ],
        cwd=ORCHESTRATOR_DIR,
    )
    procs.append(flow_proc)

    flow_proc.wait()
    shutdown()
