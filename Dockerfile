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

# Render and most other hosts set $PORT; locally it falls back to Streamlit's 8501.
# `exec` hands over to Streamlit, so it receives the stop signal and shuts down at once.
EXPOSE 8501
CMD ["sh", "-c", "exec streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]
