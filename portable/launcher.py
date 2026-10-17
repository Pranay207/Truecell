"""Entry point for the self-contained Windows portable application."""

from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

PRIVATE_IPV4_NETWORKS = tuple(
    ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def resource_root() -> Path:
    """Return PyInstaller's resource folder or the source checkout root."""
    frozen = getattr(sys, "_MEIPASS", None)
    return Path(frozen) if frozen else Path(__file__).resolve().parents[1]


def application_root() -> Path:
    """Keep portable user data beside the executable, not in bundled resources."""
    override = os.environ.get("TRUECELL_PORTABLE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _rfc1918(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and any(address in network for network in PRIVATE_IPV4_NETWORKS)


def discover_lan_address() -> str | None:
    """Find the private IPv4 selected by this computer's default route."""
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


def available_port(first: int, host: str) -> int | None:
    """Return the first available port in a small, predictable range."""
    for candidate in range(first, min(first + 10, 65536)):
        with socket.socket() as connection:
            try:
                connection.bind((host, candidate))
            except OSError:
                continue
            return candidate
    return None


def _open_when_ready(url: str) -> None:
    health = url.rstrip("/") + "/api/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health, timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.1)


def create_portable_app(data_root: Path, resources: Path, lan_host: str | None = None):
    """Create the API with explicit read-only resources and writable user data."""
    # The portable release must behave the same on computers without Tesseract.
    os.environ["TRUECELL_PORTABLE_RAPIDOCR_ONLY"] = "1"
    from truecell.api import create_app

    return create_app(
        root=data_root / "jobs",
        samples=resources / "samples",
        frontend=resources / "frontend" / "dist",
        lan_host=lan_host,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run portable Truecell on this computer.")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Allow access from a phone on the same private Wi-Fi network.",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    resources = resource_root()
    required = (
        resources / "frontend" / "dist" / "index.html",
        resources / "models" / "en_PP-OCRv5_rec_mobile.onnx",
        resources / "samples",
    )
    if any(not path.exists() for path in required):
        print("Truecell portable resources are incomplete. Extract the entire ZIP and retry.")
        return 2

    data_root = application_root() / "TruecellData"
    try:
        data_root.mkdir(parents=True, exist_ok=True)
        probe = data_root / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        print(f"Truecell cannot write its portable data folder: {data_root}")
        print("Move the complete app folder to Documents or another writable location.")
        return 2

    lan_host = discover_lan_address() if args.lan else None
    if args.lan and not lan_host:
        print("LAN mode could not find a private Wi-Fi/Ethernet IPv4 address.")
        return 2
    bind_host = "0.0.0.0" if lan_host else "127.0.0.1"
    port = available_port(args.port, bind_host)
    if port is None:
        print(f"No free local port was found between {args.port} and {min(args.port + 9, 65535)}.")
        return 2

    local_url = f"http://127.0.0.1:{port}"
    print("Truecell portable is ready.", flush=True)
    print(f"This computer: {local_url}", flush=True)
    print(f"Workspaces: {data_root}", flush=True)
    if lan_host:
        print(f"Phone (same Wi-Fi): http://{lan_host}:{port}", flush=True)
    print("Close this window or press Ctrl+C to stop Truecell.", flush=True)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(local_url,), daemon=True).start()

    from uvicorn import run

    app = create_portable_app(data_root, resources, lan_host)
    run(
        app,
        host=bind_host,
        port=port,
        proxy_headers=False,
        server_header=False,
        loop="asyncio",
        http="h11",
        ws="none",
        lifespan="on",
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
