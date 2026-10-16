"""Build a portable source/sample zip without local environments or credentials."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    destination = ROOT / "submission" / "Truecell-source-and-samples.zip"
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
        "pyproject.toml",
        "START_TRUECELL.cmd",
        "start.sh",
        "convert.py",
        "run.py",
        "pytest.ini",
        ".gitignore",
        ".gitattributes",
    }
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if (
                not path.is_file()
                or path.suffix == ".tsbuildinfo"
                or any(
                    p
                    in {
                        ".venv",
                        ".git",
                        "__pycache__",
                        ".pytest_cache",
                        "uploads",
                        "jobs",
                        "checkpoints",
                        "node_modules",
                        ".vite",
                    }
                    for p in relative.parts
                )
            ):
                continue
            if (len(relative.parts) == 1 and path.name in allowed_root) or relative.parts[
                0
            ] in allowed_dirs:
                archive.write(path, Path("Truecell") / relative)
    print(destination)
