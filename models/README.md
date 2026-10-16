# Bundled English OCR recognition model

Truecell uses the unmodified PP-OCRv5 English mobile recognition model published by RapidAI. Detection/classification assets remain supplied by the pinned RapidOCR package. We did not train any OCR model.

- Official catalog: https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml
- Download: https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/en_PP-OCRv5_rec_mobile.onnx
- SHA-256: `c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8`
- Upstream model/toolkit: PaddleOCR / RapidOCR, Apache-2.0. The unchanged model's embedded character dictionary is read by ONNX Runtime / RapidOCR.

The model ships with this repository. No runtime network download occurs. The checksum is verified before loading; invalid assets are rejected. Independent header readings can disagree and are retained in source evidence rather than presented as certain corrections.
