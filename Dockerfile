FROM python:3.12-slim-bookworm

# Install build dependencies for llama-cpp-python on ARM64 / x86_64
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency requirements
COPY pyproject.toml requirements.txt README.md ./

# Configure pip to prioritize official pre-built CPU wheels for llama-cpp-python
ENV PIP_EXTRA_INDEX_URL=https://abetlen.github.io/llama-cpp-python/whl/cpu

# Install llama-cpp-python (cached layer using prebuilt wheels)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefer-binary llama-cpp-python

# Copy application code and scripts
COPY pithon/ ./pithon/
COPY scripts/ ./scripts/
RUN chmod +x ./scripts/*.sh

# Install pithon package with package files present
RUN pip install --no-cache-dir -e .

# Create models directory
RUN mkdir -p /app/models

# Expose internal daemon port
EXPOSE 8080

# Environment variables
ENV PITHON_MODEL=/app/models/qwen2.5-0.5b-instruct-q4_k_m.gguf
ENV PYTHONUNBUFFERED=1

# Copy entrypoint
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -f http://127.0.0.1:8080/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["pithon", "serve", "--host", "0.0.0.0", "--port", "8080", "--threads", "2", "--batch", "128"]
