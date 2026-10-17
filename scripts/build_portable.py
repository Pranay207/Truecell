"""Build and archive the self-contained Windows x64 Truecell application."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "portable-build"
RELEASES = ROOT / "portable-release"
BUNDLE = RELEASES / "Truecell-Portable"
ARCHIVE = RELEASES / "Truecell-Portable-Windows-x64.zip"


def inside_workspace(path: Path) -> bool:
    """Protect cleanup so the build script only replaces its own folders."""
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return path.resolve() not in {ROOT.resolve(), ROOT.parent.resolve()}


def remove_build_path(path: Path) -> None:
    if path.exists():
        if not inside_workspace(path):
            raise RuntimeError(f"Refusing to remove a path outside the project: {path}")
        shutil.rmtree(path) if path.is_dir() else path.unlink()


def copy_release_documents() -> None:
    shutil.copy2(ROOT / "portable" / "README-FIRST.txt", BUNDLE / "README-FIRST.txt")
    for name in ("LICENSE", "THIRD_PARTY.md"):
        shutil.copy2(ROOT / name, BUNDLE / name)
    model_notices = BUNDLE / "MODEL-NOTICES"
    model_notices.mkdir(exist_ok=True)
    for name in ("README.md", "LICENSE-APACHE-2.0.txt"):
        shutil.copy2(ROOT / "models" / name, model_notices / name)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest() -> None:
    files = [path for path in BUNDLE.rglob("*") if path.is_file()]
    lines = [f"{sha256(path)}  {path.relative_to(BUNDLE).as_posix()}" for path in sorted(files)]
    (BUNDLE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_archive() -> None:
    remove_build_path(ARCHIVE)
    with zipfile.ZipFile(
        ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                archive.write(path, Path(BUNDLE.name) / path.relative_to(BUNDLE))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-archive", action="store_true", help="Build the folder only.")
    args = parser.parse_args()
    if os.name != "nt" or struct.calcsize("P") != 8:
        print("Build the portable release with 64-bit Python on Windows.")
        return 2
    if not importlib.util.find_spec("PyInstaller"):
        print("Install build tools first:")
        print(f'  "{sys.executable}" -m pip install -r requirements-build.txt')
        return 2
    required = (
        ROOT / "frontend" / "dist" / "index.html",
        ROOT / "models" / "en_PP-OCRv5_rec_mobile.onnx",
        ROOT / "portable" / "truecell.ico",
    )
    if any(not path.is_file() for path in required):
        print("Frontend, OCR model or Windows icon is missing. Restore the complete source tree.")
        return 2

    remove_build_path(BUILD)
    remove_build_path(BUNDLE)
    RELEASES.mkdir(exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--workpath",
        str(BUILD),
        "--distpath",
        str(RELEASES),
        str(ROOT / "portable" / "Truecell.spec"),
    ]
    print("Building Truecell portable Windows application...", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)
    copy_release_documents()
    write_manifest()
    if not args.no_archive:
        print("Creating portable ZIP...", flush=True)
        make_archive()
        print(f"Archive: {ARCHIVE}")
        print(f"Archive SHA-256: {sha256(ARCHIVE)}")
    print(f"Application: {BUNDLE / 'Truecell.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
