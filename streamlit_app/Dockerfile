# Hydraulic Distribution Simulator — Streamlit app container
FROM python:3.10-slim

WORKDIR /app

# System deps (minimal; numpy/scipy wheels cover most needs).
# curl is required for the HEALTHCHECK below — without it, the health
# check command itself fails and Docker reports the container as
# unhealthy even when the app is running fine.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY src/ ./src/
COPY configs/ ./configs/
COPY streamlit_app/ ./streamlit_app/
COPY .streamlit/ ./.streamlit/

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "streamlit_app/app.py", \
            "--server.port=8501", "--server.address=0.0.0.0"]
