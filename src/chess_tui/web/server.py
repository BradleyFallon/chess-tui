"""Uvicorn runner and browser launch support for ``chess-tui web``."""

from __future__ import annotations

from threading import Thread
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

import uvicorn

from .app import WebAppSettings, create_app


def run_web_server(
    settings: WebAppSettings,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Run the local server until interrupted."""

    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"
    if open_browser:
        Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")


def _open_when_ready(url: str) -> None:
    health_url = f"{url}/api/health"
    for _ in range(100):
        try:
            with urlopen(health_url, timeout=0.25) as response:  # noqa: S310
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, URLError):
            time.sleep(0.1)
