# FinVeritas image, built by .github/workflows/ci-cd.yml.
# Secrets (MONGO_URI, JWT_SECRET, API keys) are set on the host at runtime, never baked in.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so this layer is reused until requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, not root. The code stays root-owned, so the app can't change it.
RUN useradd --create-home app
USER app

# Starts the /metrics endpoint for Prometheus on 9464, then Streamlit on $PORT (Render and
# most other hosts set it; otherwise 8501). Python runs as the main process, so it receives
# the stop signal and Streamlit shuts down at once.
EXPOSE 8501 9464
CMD ["python", "-m", "finveritas.serve"]
