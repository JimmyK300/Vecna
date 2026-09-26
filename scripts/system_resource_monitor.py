# scripts/system_resource_monitor.py
import time
import os
import psutil
import csv
from datetime import datetime

TARGET_PORTS = [6900, 1337, 4200]
LOG_FILE = "system_resource_benchmark.csv"

def find_vecna_processes():
    pids = {}
    try:
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port in TARGET_PORTS:
                try:
                    proc = psutil.Process(conn.pid)
                    pids[conn.laddr.port] = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
    except Exception:
        pass
    return pids

def get_vram_usage():
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / (1024 ** 2)
            reserved = torch.cuda.memory_reserved() / (1024 ** 2)
            return round(allocated, 2), round(reserved, 2)
    except Exception:
        pass
    return 0.0, 0.0

def monitor(interval=1.0, duration=600):
    print(f"[*] Starting Vecna System Resource Monitor (Logging to {LOG_FILE})...")
    print(f"[*] Tracking Ports: {TARGET_PORTS}")
    print("=" * 85)
    
    with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp", "Total_CPU_Percent", "Total_RAM_Used_GB", "Total_RAM_Percent",
            "Core_6900_CPU", "Core_6900_RAM_MB",
            "Search_1337_CPU", "Search_1337_RAM_MB",
            "File_4200_CPU", "File_4200_RAM_MB",
            "GPU_VRAM_Alloc_MB", "GPU_VRAM_Res_MB"
        ])
        
        start_time = time.time()
        while time.time() - start_time < duration:
            procs = find_vecna_processes()
            total_cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            total_ram_gb = round(mem.used / (1024 ** 3), 2)
            total_ram_pct = mem.percent
            
            row = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                total_cpu, total_ram_gb, total_ram_pct
            ]
            
            for port in TARGET_PORTS:
                proc = procs.get(port)
                if proc and proc.is_running():
                    try:
                        cpu = proc.cpu_percent(interval=None)
                        ram_mb = round(proc.memory_info().rss / (1024 ** 2), 2)
                        row.extend([cpu, ram_mb])
                    except Exception:
                        row.extend([0.0, 0.0])
                else:
                    row.extend([0.0, 0.0])
                    
            vram_alloc, vram_res = get_vram_usage()
            row.extend([vram_alloc, vram_res])
            
            writer.writerow(row)
            f.flush()
            
            print(f"[{row[0]}] Total CPU: {total_cpu:>5}% | RAM: {total_ram_gb:>5}GB ({total_ram_pct}%) | "
                  f"Search (:1337): {row[6]:>5}% / {row[7]:>7}MB | VRAM: {vram_alloc:>7}MB")
            time.sleep(interval)

if __name__ == "__main__":
    monitor(interval=1.0, duration=600)
