"""Build the reviewed source/evidence submission ZIP from Git-tracked files."""

import hashlib
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    destination = ROOT / "submission" / "Truecell-2.0-Submission.zip"
    checksum = destination.with_suffix(destination.suffix + ".sha256")
    destination.parent.mkdir(exist_ok=True)
    allowed_dirs = {
        "truecell",
        "tests",
        "eval",
        "scripts",
        "docs",
        "reports",
        "samples",
        "outputs",
        "models",
        "portable",
        "third_party_licenses",
        ".github",
        "frontend",
    }
    allowed_root = {
        "README.md",
        "JUDGE_START_HERE.txt",
        "THIRD_PARTY.md",
        "LICENSE",
        "requirements.txt",
        "requirements-lock.txt",
        "requirements-dev.txt",
        "requirements-build.txt",
        "pyproject.toml",
        "BUILD_PORTABLE.cmd",
        "START_TRUECELL.cmd",
        "start.sh",
        "convert.py",
        "run.py",
        "pytest.ini",
        ".gitignore",
        ".gitattributes",
    }
    excluded_parts = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "uploads",
        "jobs",
        "checkpoints",
        "node_modules",
        ".vite",
        "tmp",
        "submission",
        "portable-build",
        "portable-release",
    }
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    )
    destination.unlink(missing_ok=True)
    checksum.unlink(missing_ok=True)
    file_count = 0
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for tracked_name in sorted(name for name in tracked if name):
            relative = Path(tracked_name)
            path = ROOT / relative
            if (
                not path.is_file()
                or path.suffix == ".tsbuildinfo"
                or any(part in excluded_parts for part in relative.parts)
            ):
                continue
            if (len(relative.parts) == 1 and path.name in allowed_root) or relative.parts[
                0
            ] in allowed_dirs:
                archive.write(path, Path("Truecell") / relative)
                file_count += 1
    required = {
        "Truecell/README.md",
        "Truecell/JUDGE_START_HERE.txt",
        "Truecell/run.py",
        "Truecell/frontend/dist/index.html",
        "Truecell/models/en_PP-OCRv5_rec_mobile.onnx",
        "Truecell/portable/Truecell.spec",
    }
    with zipfile.ZipFile(destination) as archive:
        missing = required.difference(archive.namelist())
    if missing:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Submission archive is incomplete: {sorted(missing)}")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(f"Archive: {destination}")
    print(f"Files: {file_count}")
    print(f"SHA-256: {digest}")
