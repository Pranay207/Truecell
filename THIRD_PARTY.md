# Third-party credits

The extraction, OCR, rendering, UI and spreadsheet libraries do substantial underlying work. Truecell does not claim to have authored their algorithms or models.

| Library | Role | Upstream / license reference |
|---|---|---|
| pdfplumber / pdfminer.six | Native text and table geometry | https://github.com/jsvine/pdfplumber (MIT); https://github.com/pdfminer/pdfminer.six (MIT) |
| PyMuPDF / MuPDF | PDF opening, per-page rendering and sample rasterization | https://pymupdf.readthedocs.io/en/latest/about.html (AGPL-3.0 or commercial) |
| RapidOCR ONNX | Bundled detection, classification and recognition models | https://github.com/RapidAI/RapidOCR (Apache-2.0; see bundled model notices) |
| ONNX Runtime | CPU model inference | https://github.com/microsoft/onnxruntime (MIT) |
| OpenCV | Deskew, denoising and grid morphology | https://github.com/opencv/opencv (Apache-2.0) |
| Tesseract / pytesseract | Optional second OCR engine / Python wrapper | https://github.com/tesseract-ocr/tesseract (Apache-2.0); https://github.com/madmaze/pytesseract (Apache-2.0) |
| NumPy | Image arrays | https://numpy.org (BSD-3-Clause) |
| Pillow | Images, TIFF frames and sample degradation | https://python-pillow.org (HPND) |
| openpyxl | Typed Excel workbooks and styles | https://openpyxl.readthedocs.io (MIT) |
| React / React DOM | Responsive local studio interface | https://react.dev (MIT) |
| Vite / TypeScript | Frontend build and type checking | https://vite.dev (MIT); https://www.typescriptlang.org (Apache-2.0) |
| FastAPI / Starlette / Uvicorn | Loopback-only local HTTP API and static serving | https://fastapi.tiangolo.com (MIT); https://www.starlette.io (BSD-3-Clause); https://www.uvicorn.org (BSD-3-Clause) |
| ReportLab | Dummy PDF generation | https://www.reportlab.com (BSD) |
| pytest | Regression tests | https://pytest.org (MIT) |
| Python | Application runtime | https://www.python.org (PSF license) |

Optional vision requests use the configured provider's API under that provider's terms. No network provider was used to produce the offline benchmark. Dependencies bring additional transitive libraries; installed distributions contain their individual notices. Preserve upstream notices when redistributing dependencies or models.

The unmodified **PP-OCRv5 English mobile recognizer** is redistributed in `models/en_PP-OCRv5_rec_mobile.onnx`, from the RapidAI official model catalog / PaddleOCR ecosystem under Apache-2.0. [Model source, hash and licence](models/README.md) accompany the asset; `models/LICENSE-APACHE-2.0.txt` preserves the licence. Truecell did not train this model. RapidOCR's pinned package supplies detection/classification assets.

Ruff (development formatting/linting) is MIT licensed: https://github.com/astral-sh/ruff.

The external audit references public Camelot, tabula-java and W3C documents and records URLs/hashes. A separate transfer audit uses published dummy PDFs and author-provided truth from https://github.com/rayanakarthikeyan/damnlens-ai-agent. Those inputs and the competitor implementation are not redistributed. No competitor code is imported, executed or incorporated. General recovery, geometry, constraint and review logic was implemented independently with AI coding assistance; there is no claim of exclusive invention of table extraction or arithmetic validation.
