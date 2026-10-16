"""Launch the local FastAPI server and prebuilt React application."""

from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def _rfc1918(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and any(address in network for network in PRIVATE_IPV4_NETWORKS)


def discover_lan_address() -> str | None:
    """Find the private IPv4 selected by the computer's default route."""
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 80))
            candidates.append(connection.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(
            record[4][0]
            for record in socket.getaddrinfo(
                socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM
            )
        )
    except OSError:
        pass
    return next((address for address in candidates if _rfc1918(address)), None)


def _open_when_ready(url: str) -> None:
    """Open the local app only after its health endpoint begins responding."""
    health = url.rstrip("/") + "/api/health"
    for _ in range(80):
        try:
            with urllib.request.urlopen(health, timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.1)


def modern(port: int, no_browser: bool, lan: bool = False) -> int:
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        print("The supplied frontend build is missing (frontend/dist/index.html).")
        print("Restore the complete project, or run npm install && npm run build in frontend/.")
        return 2
    local_url = f"http://127.0.0.1:{port}"
    lan_host = discover_lan_address() if lan else None
    if lan and not lan_host:
        print("LAN mode could not find a private Wi-Fi/Ethernet IPv4 address.")
        print("Connect this computer to the same private network as the phone, then try again.")
        return 2
    if not no_browser:
        threading.Thread(target=_open_when_ready, args=(local_url,), daemon=True).start()
    print(f"This computer: {local_url}", flush=True)
    if lan_host:
        print(f"Phone (same Wi-Fi): http://{lan_host}:{port}", flush=True)
        print("LAN access remains available until this server is stopped.", flush=True)
    environment = os.environ.copy()
    if lan_host:
        environment["TRUECELL_LAN_HOST"] = lan_host
    else:
        environment.pop("TRUECELL_LAN_HOST", None)
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "truecell.api:app",
            "--host",
            "0.0.0.0" if lan_host else "127.0.0.1",
            "--port",
            str(port),
            "--no-proxy-headers",
        ],
        cwd=ROOT,
        env=environment,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Truecell on this computer.")
    parser.add_argument("--port", "--server.port", dest="port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Allow the modern app from a phone on the same private Wi-Fi network.",
    )
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    return modern(args.port, args.no_browser, args.lan)


if __name__ == "__main__":
    raise SystemExit(main())
