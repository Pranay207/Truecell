FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRUECELL_TRUST_LOCAL_PROXY=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        libgl1 \
        libglib2.0-0 \
        tesseract-ocr \
        tesseract-ocr-hin \
        tesseract-ocr-tel \
    && tesseract --list-langs 2>/dev/null | grep -qx eng \
    && tesseract --list-langs 2>/dev/null | grep -qx hin \
    && tesseract --list-langs 2>/dev/null | grep -qx tel \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
ARG PIP_TRUSTED_HOST
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY truecell/ ./truecell/
COPY models/ ./models/
COPY samples/ ./samples/
COPY LICENSE THIRD_PARTY.md ./
COPY third_party_licenses/ ./third_party_licenses/
# The checked-in bundle is built and freshness-checked by the frontend CI job.
# Keeping npm outside this image avoids a registry dependency on Docker build hosts where
# npm's registry client fails behind an intercepting proxy.
COPY frontend/dist/ ./frontend/dist/

RUN mkdir -p /app/outputs/jobs \
    && addgroup --system truecell \
    && adduser --system --ingroup truecell --home /app truecell \
    && chown -R truecell:truecell /app

USER truecell
VOLUME ["/app/outputs"]
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/api/health', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "truecell.api:app", "--host", "0.0.0.0", "--port", "8501", "--no-proxy-headers"]
