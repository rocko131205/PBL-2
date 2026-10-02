# FinVeritas — production image.
# Built, smoke-tested, scanned and published by .github/workflows/ci-cd.yml.
# Secrets (JWT_SECRET, MONGO_URI, LLM_API_KEY, …) are injected at runtime by the
# hosting platform — never baked into the image.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pick up Debian security fixes newer than the base image (the Trivy gate in CI
# fails on fixable HIGH/CRITICAL CVEs).
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Unprivileged runtime user. Code stays root-owned, so the app can't modify itself.
RUN useradd --create-home --uid 10001 appuser

COPY app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY finveritas ./finveritas
COPY scripts/make_admin.py ./scripts/make_admin.py

# Shown in the login footer, so a rolling update is visible in the UI. Declared late so a
# new version doesn't invalidate the dependency layers. CI passes the commit (sha-xxxxxxx).
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

USER appuser

# Most PaaS hosts (Render, Railway, Cloud Run) inject $PORT; default to Streamlit's 8501.
ENV PORT=8501
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/_stcore/health', timeout=4)"

CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --server.fileWatcherType=none"]
