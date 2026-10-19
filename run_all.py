"""
run_all.py — One-Command Launcher for AI Tech Consultant
--------------------------------------------------------
Why this file exists:
Starts all three services with a single command (`python run_all.py`):
- Task 1: The Knowledge Brain API & Chat UI      -> http://127.0.0.1:8001
- Task 2: The Inbox Agent API & Review UI        -> http://127.0.0.1:8002
- Task 3: Meeting to Scope of Work API & UI      -> http://127.0.0.1:8003

You can also run:
- `python run_all.py --eval` to run all 70 evaluation cases across Task 1, Task 2, and Task 3.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run_all_evals():
    """Starts Task 1 API in the background, runs all 3 evaluation scripts, and exits cleanly."""
    print("=" * 72)
    print("Starting Task 1 (Knowledge Brain API on :8001) for end-to-end evals...")
    print("=" * 72)
    t1_proc = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(ROOT / "knowledge-brain"),
    )
    time.sleep(2.5)
    try:
        for folder, script in [
            ("knowledge-brain", "eval_task1.py"),
            ("inbox-agent", "eval_task2.py"),
            ("meeting-to-scope", "eval_task3.py"),
        ]:
            print(f"\n>>> Running {folder}/{script} ...")
            subprocess.run([sys.executable, script], cwd=str(ROOT / folder), check=True)
    finally:
        t1_proc.terminate()
        t1_proc.wait(timeout=5)
    print("\nAll 3 task evaluation suites completed successfully!")

def main():
    if "--eval" in sys.argv:
        run_all_evals()
        return

    services = [
        ("Task 1 — Knowledge Brain (:8001)", ROOT / "knowledge-brain", "8001"),
        ("Task 2 — Inbox Agent     (:8002)", ROOT / "inbox-agent", "8002"),
        ("Task 3 — Meeting to Scope(:8003)", ROOT / "meeting-to-scope", "8003"),
    ]

    procs = []
    print("=" * 72)
    print("Launching AI Tech Consultant (All 3 Connected Python Services)...")
    print("=" * 72)

    try:
        for name, folder, port in services:
            print(f"Starting {name} -> http://127.0.0.1:{port}")
            p = subprocess.Popen([sys.executable, "main.py"], cwd=str(folder))
            procs.append(p)
            time.sleep(1.0)

        print("\nAll 3 services are live!")
        print("  1. Knowledge Brain UI : http://127.0.0.1:8001")
        print("  2. Inbox Agent UI     : http://127.0.0.1:8002")
        print("  3. Scope Builder UI   : http://127.0.0.1:8003")
        print("\nPress Ctrl+C at any time to stop all services.")

        try:
            webbrowser.open("http://127.0.0.1:8001")
        except Exception:
            pass

        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        for p in procs:
            p.terminate()

if __name__ == "__main__":
    main()
