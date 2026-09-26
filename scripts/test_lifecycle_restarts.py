# scripts/test_lifecycle_restarts.py
"""
Script kiểm thử tự động chu trình: Khởi động -> Warm up & Search -> Tắt hệ thống -> Kiểm tra rác/zombie port/VRAM -> Khởi động lại.
Lặp lại N chu kỳ để phát hiện lỗi treo cổng (WinError 10048), rò rỉ VRAM qua các lần restart, hoặc tiến trình ma (zombie process).
"""

import subprocess
import time
import sys
import os
import psutil
import requests

TARGET_PORTS = [6900, 1337, 4200]
FRONTEND_PORT = 5173
PYTHON_EXEC = sys.executable
HEALTH_URL_CORE = "http://127.0.0.1:6900/api/collections"
HEALTH_URL_SEARCH = "http://127.0.0.1:1337/api/health"
HEALTH_URL_FILE = "http://127.0.0.1:4200/api/health"

def check_ports_free():
    busy = []
    for conn in psutil.net_connections(kind='inet'):
        if conn.status == psutil.CONN_LISTEN and conn.laddr.port in TARGET_PORTS + [FRONTEND_PORT]:
            busy.append((conn.laddr.port, conn.pid))
    return busy

def kill_zombie_vecna():
    """Dọn dẹp triệt để các tiến trình ma nếu còn kẹt cổng."""
    busy = check_ports_free()
    for port, pid in busy:
        try:
            p = psutil.Process(pid)
            print(f"[!] Force killing zombie process {p.name()} (PID: {pid}) holding port {port}")
            p.kill()
        except Exception:
            pass
    time.sleep(1)

def get_vram_mb():
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.memory_allocated() / (1024 ** 2), 2)
    except Exception:
        pass
    return 0.0

def wait_for_healthy(timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r1 = requests.get(HEALTH_URL_CORE, timeout=1)
            r2 = requests.get(HEALTH_URL_SEARCH, timeout=1)
            r3 = requests.get(HEALTH_URL_FILE, timeout=1)
            if r1.status_code == 200 and r2.status_code == 200 and r3.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def run_test_query():
    url = "http://127.0.0.1:6900/api/search_multimodal?q=xe+hoi&limit=10"
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=15)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            total = resp.json().get("total", 0)
            return True, elapsed, total
        return False, elapsed, 0
    except Exception as e:
        return False, time.time() - t0, str(e)

def run_lifecycle_cycles(total_cycles=5):
    print("=" * 80)
    print(f"[*] BẮT ĐẦU KIỂM THỬ VÒNG ĐỜI: {total_cycles} CHU KỲ KHỞI ĐỘNG - TẮT - RESTART")
    print("=" * 80)
    
    kill_zombie_vecna()
    
    results = []
    
    for cycle in range(1, total_cycles + 1):
        print(f"\n--- [CHU KỲ {cycle}/{total_cycles}] ---")
        
        # 1. Kiểm tra cổng sạch trước khi bật
        busy_before = check_ports_free()
        if busy_before:
            print(f"[-] LỖI: Các cổng đang bị kẹt trước khi bật: {busy_before}")
            kill_zombie_vecna()
        
        vram_start = get_vram_mb()
        print(f"[*] Khởi động server (aic51-cli serve)... [VRAM trước bật: {vram_start} MB]")
        t_start = time.time()
        
        # Chạy serve process
        proc = subprocess.Popen(
            [PYTHON_EXEC, "-m", "aic51.cli", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=os.getcwd()
        )
        
        # 2. Đợi server sẵn sàng (Healthcheck)
        is_healthy = wait_for_healthy(timeout=45)
        startup_time = round(time.time() - t_start, 2)
        
        if not is_healthy:
            print(f"[-] THẤT BẠI: Server không thể sẵn sàng sau 45s tại chu kỳ {cycle}!")
            proc.terminate()
            kill_zombie_vecna()
            results.append({"cycle": cycle, "status": "FAIL_STARTUP", "startup_time": startup_time})
            continue
            
        print(f"[+] Server sẵn sàng sau {startup_time}s")
        
        # 3. Test tìm kiếm (Warm-up & Functional check)
        success, q_time, info = run_test_query()
        print(f"[*] Test query ('xe hoi'): {'SUCCESS' if success else 'FAIL'} trong {q_time:.2f}s (Total: {info})")
        
        # 4. Tắt server (Graceful Shutdown)
        print(f"[*] Gửi tín hiệu tắt server (SIGTERM/Ctrl+C)...")
        t_stop = time.time()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print("[!] Quá thời gian 10s: Buộc kill tiến trình chính!")
            proc.kill()
            
        shutdown_time = round(time.time() - t_stop, 2)
        print(f"[+] Tiến trình chính đã tắt sau {shutdown_time}s")
        
        # Chờ 2s để OS giải phóng socket
        time.sleep(2)
        
        # 5. Kiểm tra rò rỉ cổng và tiến trình ma (Zombie check)
        busy_after = check_ports_free()
        vram_end = get_vram_mb()
        
        zombie_detected = len(busy_after) > 0
        if zombie_detected:
            print(f"[-] CẢNH BÁO ZOMBIE: Các cổng vẫn bị chiếm giữ sau khi tắt: {busy_after}")
            kill_zombie_vecna()
        else:
            print(f"[+] TẤT CẢ CỔNG ĐÃ ĐƯỢC GIẢI PHÓNG SẠCH SẼ ({TARGET_PORTS})")
            
        print(f"[*] VRAM sau khi tắt: {vram_end} MB (Độ chênh lệch: {round(vram_end - vram_start, 2)} MB)")
        
        results.append({
            "cycle": cycle,
            "status": "PASS" if is_healthy and success and not zombie_detected else "WARN/FAIL",
            "startup_time": startup_time,
            "query_time": round(q_time, 2),
            "shutdown_time": shutdown_time,
            "zombies": len(busy_after),
            "vram_delta": round(vram_end - vram_start, 2)
        })
        
        time.sleep(2)
        
    print("\n" + "=" * 80)
    print("BẢNG TỔNG KẾT KIỂM THỬ KHỞI ĐỘNG - TẮT - RESTART:")
    print(f"{'Chu kỳ':<8} | {'Trạng thái':<10} | {'Bật (s)':<8} | {'Query (s)':<10} | {'Tắt (s)':<8} | {'Zombie':<8} | {'VRAM Delta'}")
    print("-" * 80)
    for r in results:
        print(f"{r['cycle']:<8} | {r['status']:<10} | {r.get('startup_time', '-'):<8} | {r.get('query_time', '-'):<10} | {r.get('shutdown_time', '-'):<8} | {r.get('zombies', '-'):<8} | {r.get('vram_delta', '-')} MB")
    print("=" * 80)

if __name__ == "__main__":
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    run_lifecycle_cycles(cycles)
