"""
Local Server & Proxy for DRES Submission Portal
AI Challenge 2026 Finals
"""

import http.server
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
TARGET_SERVER = "https://eventretrieval.one"


class DRESProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.path = "/dres_submitter.html"
            return super().do_GET()

        if self.path.startswith("/proxy/"):
            self._handle_proxy("GET")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/proxy/"):
            self._handle_proxy("POST")
        else:
            self.send_error(404, "Not Found")

    def _handle_proxy(self, method: str):
        target_path = self.path[len("/proxy"):]
        target_url = TARGET_SERVER + target_path

        body_data = None
        if method == "POST":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body_data = self.rfile.read(content_length)

        headers = {
            "User-Agent": "DRES-Local-Proxy/1.0",
            "Content-Type": self.headers.get("Content-Type", "application/json"),
        }

        req = urllib.request.Request(target_url, data=body_data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                resp_code = resp.status
                resp_headers = dict(resp.headers)
                resp_data = resp.read()

                self.send_response(resp_code)
                self.send_header("Content-Type", resp_headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "*")
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)

        except urllib.error.HTTPError as e:
            err_data = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Content-Length", str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)

        except Exception as e:
            err_json = json.dumps({"status": False, "description": f"Proxy Error: {str(e)}"}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Content-Length", str(len(err_json)))
            self.end_headers()
            self.wfile.write(err_json)


def run_server():
    port = PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    server_address = ("", port)
    try:
        httpd = http.server.HTTPServer(server_address, DRESProxyHandler)
    except OSError:
        port = port + 1
        server_address = ("", port)
        httpd = http.server.HTTPServer(server_address, DRESProxyHandler)

    url = f"http://localhost:{port}/dres_submitter.html"
    print("=" * 60)
    print("  DRES SUBMISSION PORTAL - LOCAL SERVER & PROXY")
    print("=" * 60)
    print(f"[*] May chu dang chay tai: {url}")
    print("[*] Da kich hoat CORS Proxy giup loai bo hoan toan loi chan mang.")
    print("[*] Nhan Ctrl+C hoac dong cua so de dung.")
    print("=" * 60)

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Dang tat server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
