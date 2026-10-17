# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

PROJECT = Path(SPECPATH).resolve().parent

datas = [
    (str(PROJECT / "frontend" / "dist"), "frontend/dist"),
    (str(PROJECT / "models"), "models"),
    (str(PROJECT / "samples"), "samples"),
]
binaries = []
hiddenimports = [
    "fitz",
    "multipart",
    "uvicorn.logging",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on",
]

# RapidOCR loads its YAML and three ONNX assets dynamically. ONNX Runtime,
# OpenCV and Shapely native binaries are handled by PyInstaller's hooks.
datas += collect_data_files("rapidocr_onnxruntime")
hiddenimports += collect_submodules("rapidocr_onnxruntime")

datas += collect_data_files("pdfminer")

# Truecell records dependency versions in its checkpoint signature. Preserve
# the installed distribution metadata so those audit values remain available.
for distribution in (
    "PyMuPDF",
    "pdfplumber",
    "pdfminer.six",
    "rapidocr-onnxruntime",
    "onnxruntime",
    "opencv-python",
    "pytesseract",
    "openpyxl",
    "Pillow",
):
    datas += copy_metadata(distribution)

analysis = Analysis(
    [str(PROJECT / "portable" / "launcher.py")],
    pathex=[str(PROJECT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "onnx",
        "onnxruntime.quantization",
        "onnxruntime.tools",
        "onnxruntime.transformers",
        "pandas",
        "pyarrow",
        "pytest",
        "reportlab",
        "shapely.tests",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Truecell",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(PROJECT / "portable" / "truecell.ico")],
)

bundle = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Truecell-Portable",
)
