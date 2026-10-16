"""One-command local setup, diagnostics and launch without system-level installs."""

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import subprocess
import sys
import venv
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def port_number(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535.")
    return port


def available_port(first: int, bind_host: str = "127.0.0.1") -> int | None:
    for candidate in range(first, min(first + 10, 65536)):
        with socket.socket() as connection:
            try:
                connection.bind((bind_host, candidate))
                return candidate
            except OSError:
                continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--judge-test", action="store_true")
    parser.add_argument("--port", type=port_number, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--lan",
        action="store_true",
        help="Allow the modern app from a phone on the same private Wi-Fi network.",
    )
    args = parser.parse_args()
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        print(
            "Use 64-bit Python 3.10, 3.11 or 3.12. No system software is installed automatically."
        )
        return 2
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if Path(sys.executable).resolve() != python.resolve():
        if not python.exists():
            if args.offline:
                print("Project environment missing; run without --offline for initial setup.")
                return 2
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
        return subprocess.call(
            [str(python), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT
        )
    missing = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if "==" not in line:
            continue
        name, pinned = line.split("==", 1)
        try:
            if version(name) != pinned:
                missing.append(line)
        except PackageNotFoundError:
            missing.append(line)
    if missing:
        if args.offline:
            print("Missing or mismatched packages: " + ", ".join(missing))
            return 2
        code = subprocess.call(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--use-feature=truststore",
                "-r",
                str(ROOT / "requirements.txt"),
            ],
            cwd=ROOT,
        )
        if code:
            return code
    model = ROOT / "models/en_PP-OCRv5_rec_mobile.onnx"
    if (
        not model.is_file()
        or hashlib.sha256(model.read_bytes()).hexdigest()
        != "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8"
    ):
        print(
            "The bundled OCR asset is missing or changed. Extract the complete project ZIP again."
        )
        return 2
    print(
        f"Environment ready: Python {sys.version.split()[0]}, bundled English OCR checksum verified."
    )
    if args.check:
        return 0
    if args.judge_test:
        return subprocess.call([str(python), str(ROOT / "scripts/judge_check.py")], cwd=ROOT)
    port = available_port(args.port, "0.0.0.0" if args.lan else "127.0.0.1")
    if port is None:
        print("No free local port; choose --port with another value.")
        return 2
    command = [
        str(python),
        str(ROOT / "run.py"),
        "--port",
        str(port),
    ]
    if args.no_browser:
        command.append("--no-browser")
    if args.lan:
        command.append("--lan")
        print("Starting Truecell for this computer and the same private network.")
    else:
        print(f"Truecell: http://127.0.0.1:{port}")
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
