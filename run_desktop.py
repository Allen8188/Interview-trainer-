from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser

import uvicorn
from app.main import app as fastapi_app


def _open_browser_later(url: str, delay_sec: float = 1.5) -> None:
    def _worker() -> None:
        time.sleep(delay_sec)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    url = f"http://{host}:{port}"

    if not _port_available(host, port):
        print(f"[ERROR] Port {port} is already in use. Set PORT env var and retry.")
        input("Press Enter to exit...")
        return

    print(f"Interview Trainer starting at: {url}")
    if os.environ.get("IT_OPEN_BROWSER", "1") == "1":
        _open_browser_later(url)

    uvicorn.run(fastapi_app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
