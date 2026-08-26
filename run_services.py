"""Single-terminal concurrent runner for VoiceVoyage backend services.

Starts both:
  - Phoneme Service on port 8001 (POST /assess, GET /health)
  - Dynamic Modules Service on port 8002 (POST /module, GET /health)

Streams output from both processes in real time with colored service prefixes.
Gracefully terminates both on Ctrl+C.
"""

import os
import sys
import subprocess
import threading
import signal
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PHONEME_DIR = os.path.join(REPO_ROOT, "phoneme_service")
DYNAMIC_DIR = os.path.join(REPO_ROOT, "dynamic_modules_service")

CYAN = "\033[96m"
MAGENTA = "\033[95m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def stream_output(pipe, prefix: str, color: str):
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            clean_line = line.rstrip()
            if clean_line:
                print(f"{color}[{prefix}]{RESET} {clean_line}", flush=True)
    except Exception:
        pass
    finally:
        pipe.close()


def main():
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul 2>&1")
        except Exception:
            pass

    print(f"\n{BOLD}{GREEN}======================================================{RESET}")
    print(f"{BOLD}{GREEN} VoiceVoyage Backend Services — Single Terminal Runner {RESET}")
    print(f"{BOLD}{GREEN}======================================================{RESET}")
    print(f"{CYAN}• Phoneme Service:{RESET}        http://localhost:8001  (POST /assess)")
    print(f"{MAGENTA}• Dynamic Modules Service:{RESET}http://localhost:8002  (POST /module)")
    print(f"{YELLOW}Press CTRL+C at any time to shut down both services.{RESET}\n")

    py_exe = sys.executable

    phoneme_proc = subprocess.Popen(
        [py_exe, "-X", "utf8", "-m", "uvicorn", "main:app", "--port", "8001", "--host", "0.0.0.0"],
        cwd=PHONEME_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )

    dynamic_proc = subprocess.Popen(
        [py_exe, "-X", "utf8", "-m", "uvicorn", "main:app", "--port", "8002", "--host", "0.0.0.0"],
        cwd=DYNAMIC_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )

    t1 = threading.Thread(
        target=stream_output,
        args=(phoneme_proc.stdout, "PHONEME :8001", CYAN),
        daemon=True,
    )
    t2 = threading.Thread(
        target=stream_output,
        args=(dynamic_proc.stdout, "MODULES :8002", MAGENTA),
        daemon=True,
    )

    t1.start()
    t2.start()

    try:
        while True:
            p1_ret = phoneme_proc.poll()
            p2_ret = dynamic_proc.poll()
            if p1_ret is not None:
                print(f"{RED}[PHONEME :8001] Process exited with code {p1_ret}{RESET}", flush=True)
                break
            if p2_ret is not None:
                print(f"{RED}[MODULES :8002] Process exited with code {p2_ret}{RESET}", flush=True)
                break
            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Shutting down both services...{RESET}", flush=True)

    finally:
        for proc in (phoneme_proc, dynamic_proc):
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    proc.kill()

        print(f"{GREEN}Both services stopped cleanly.{RESET}\n")


if __name__ == "__main__":
    main()
