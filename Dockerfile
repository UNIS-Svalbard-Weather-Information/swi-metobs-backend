ARG PYTHON_VERSION=3.14
ARG API_VERSION=3.X.X

# Stage 1: Dependency resolution
FROM astral/uv:python${PYTHON_VERSION}-bookworm-slim AS uv
WORKDIR /swi
COPY pyproject.toml uv.lock ./
# Export the locked, hashed set: the image installs exactly what uv.lock pins.
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt

# Stage 2: Build
FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /swi
COPY --from=uv /swi/requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Stage 3: Runtime
FROM python:${PYTHON_VERSION}-slim
ARG API_VERSION
ARG PYTHON_VERSION
WORKDIR /swi

# Install curl and clean up
RUN apt-get update && \
    apt-get install -y curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy only necessary files from the builder stage
COPY --from=builder /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
# The service never installs packages at runtime: remove pip (and its vendored copies
# of urllib3, msgpack, ...) so they are neither exposed nor flagged by image scanners.
RUN python -m pip uninstall -y pip setuptools wheel 2>/dev/null || true

# Copy application code
COPY . .
RUN echo "VERSION = '${API_VERSION}'" > ./app/version.py

# Environment variables
ENV PORT=8085
ENV WORKERS=4
ENV API_ROOT_PATH="/public"

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose the port
EXPOSE $PORT

# Run the app
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --root-path ${API_ROOT_PATH}"]