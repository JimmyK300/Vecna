"""Single-command runner for Vecna (AIC51) Multimodal Retrieval System.
Starts Search (1337), File (4200), and Core Gateway (6900) in one terminal.
Access the full Web UI at: http://localhost:6900
"""

import os
import sys
import time
import signal
import subprocess
import webbrowser
from pathlib import Path

def main():
    repo_root = Path(__file__).resolve().parent
    aic51_src = repo_root / "aic51-src"
    
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(aic51_src) + (os.pathsep + current_pythonpath if current_pythonpath else "")
    python_exe = sys.executable
    
    print("=" * 70)
    print("           STARTING VECNA MULTIMODAL VIDEO SEARCH SYSTEM           ")
    print("=" * 70)
    print(f"Python:     {python_exe}")
    print(f"Workspace:  {repo_root}")
    print(f"Indices:    workspace/mmap_indices (numpy.mmap engine, zero-Docker)")
    print("-" * 70)
    
    processes = []
    
    # 1. Search Backend (Port 1337)
    cmd_search = [
        python_exe, "-m", "uvicorn",
        "aic51.packages.webui.backend.search:app",
        "--host", "0.0.0.0",
        "--port", "1337",
        "--log-level", "info",
    ]
    p_search = subprocess.Popen(cmd_search, env=env, cwd=str(repo_root))
    processes.append(("Search Backend (1337)", p_search))
    
    # 2. File Backend (Port 4200)
    cmd_file = [
        python_exe, "-m", "uvicorn",
        "aic51.packages.webui.backend.file:app",
        "--host", "0.0.0.0",
        "--port", "4200",
        "--log-level", "warning",
    ]
    p_file = subprocess.Popen(cmd_file, env=env, cwd=str(repo_root))
    processes.append(("File Backend (4200)", p_file))
    
    # 3. Core Gateway & WebUI (Port 6900)
    cmd_core = [
        python_exe, "-m", "uvicorn",
        "aic51.packages.webui.backend.core:app",
        "--host", "0.0.0.0",
        "--port", "6900",
        "--log-level", "info",
    ]
    p_core = subprocess.Popen(cmd_core, env=env, cwd=str(repo_root))
    processes.append(("Core Gateway (6900)", p_core))
    
    print("\n[+] Initializing all 3 microservices concurrently:")
    print("    * Search Engine:   http://localhost:1337")
    print("    * File / Media:    http://localhost:4200")
    print("    * Core Gateway:    http://localhost:6900  <-- (OPEN THIS LINK)")
    print("-" * 70)
    print("Press CTRL+C anytime to stop all services cleanly.\n")
    
    # Wait until Search backend is ready, then launch browser
    def open_browser():
        import urllib.request
        for _ in range(90):
            time.sleep(1)
            try:
                with urllib.request.urlopen("http://localhost:1337/api/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                continue
        time.sleep(1)
        print("\n" + "=" * 70)
        print("  >>> ALL VECNA SERVICES ARE ONLINE AND READY! <<<")
        print("  Web UI: http://localhost:6900")
        print("=" * 70 + "\n")
        try:
            webbrowser.open("http://localhost:6900")
        except Exception:
            pass
            
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        # Keep runner alive while monitoring child processes
        while True:
            for name, proc in processes:
                ret = proc.poll()
                if ret is not None:
                    print(f"\n[!] Process {name} exited with code {ret}")
                    raise KeyboardInterrupt
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\nShutting down Vecna services...")
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for name, proc in processes:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("All Vecna services stopped. Goodbye!")

if __name__ == "__main__":
    main()
