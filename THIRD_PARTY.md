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
| Streamlit / pandas | Upload UI and table preview | https://streamlit.io (Apache-2.0); https://pandas.pydata.org (BSD-3-Clause) |
| ReportLab | Dummy PDF generation | https://www.reportlab.com (BSD) |
| pytest | Regression tests | https://pytest.org (MIT) |
| Python | Application runtime | https://www.python.org (PSF license) |

Optional vision requests use the configured provider's API under that provider's terms. No network provider was used to produce the offline benchmark. Dependencies bring additional transitive libraries; installed distributions contain their individual notices. Preserve upstream notices when redistributing dependencies or models.
