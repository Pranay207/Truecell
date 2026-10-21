FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRUECELL_TRUST_LOCAL_PROXY=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY truecell/ ./truecell/
COPY models/ ./models/
COPY samples/ ./samples/
COPY --from=frontend-build /build/frontend/dist/ ./frontend/dist/

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
