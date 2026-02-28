ARG PYTHON_VERSION=3.14
ARG API_VERSION=3.X.X

# Stage 1: Dependency resolution
FROM astral/uv:python${PYTHON_VERSION}-bookworm-slim AS uv
WORKDIR /swi
COPY pyproject.toml .
RUN uv pip compile pyproject.toml > requirements.txt

# Stage 2: Build
FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /swi
COPY --from=uv /swi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

# Copy application code
COPY . .
RUN echo "VERSION = '${API_VERSION}'" > ./app/version.py

# Environment variables
ENV PORT=8085
ENV WORKERS=4
ENV API_ROOT_PATH="/public"

# Healthcheck
# HEALTHCHECK --interval=30s --timeout=3s \
#     CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose the port
EXPOSE $PORT

# Run the app
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS} --root-path ${API_ROOT_PATH}
