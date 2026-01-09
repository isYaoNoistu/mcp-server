# Simple, production-ready Dockerfile for the mcp-server FastAPI app.
# Build: docker build -t mcp-server:latest .
# Run:   docker run -p 8000:8000 --name mcp-server mcp-server:latest

# 提示：若使用docker镜像启动服务，则部分mcp功能会失效，后续会适配处理

FROM python:3.11-slim

# Keep Python output unbuffered (helpful for logs)
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies required for some Python packages (build-essential
# is safe and small on slim; remove if not needed). Keep image small afterwards.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage build cache
COPY requirements.txt .

# Upgrade pip and install Python dependencies
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user for running the app and set ownership
RUN useradd -m app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Entrypoint: run uvicorn serving the FastAPI app defined in mcp_server.py
# Adjust --workers according to the CPU / workload; set to 1 for lower memory usage.
CMD ["uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]