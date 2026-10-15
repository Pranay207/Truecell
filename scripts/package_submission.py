"""Build a portable source/sample zip without local environments or credentials."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    destination = ROOT / "submission" / "Truecell-source-and-samples.zip"
    destination.parent.mkdir(exist_ok=True)
    allowed_dirs = {"truecell", "tests", "eval", "scripts", "docs", "reports", "samples", "outputs", ".github"}
    allowed_root = {"README.md", "THIRD_PARTY.md", "LICENSE", "requirements.txt", "requirements-lock.txt",
                    "convert.py", "app.py", "run.py", "pytest.ini", ".gitignore", ".gitattributes"}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(p in {".venv", ".git", "__pycache__", ".pytest_cache", "uploads"} for p in relative.parts):
                continue
            if (len(relative.parts) == 1 and path.name in allowed_root) or relative.parts[0] in allowed_dirs:
                archive.write(path, Path("Truecell") / relative)
    print(destination)
