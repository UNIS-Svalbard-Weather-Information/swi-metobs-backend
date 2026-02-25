ARG PYTHON_VERSION=3.13

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
WORKDIR /swi

# Copy only necessary files from the builder stage
COPY --from=builder /usr/local/lib/python${PYTHON_VERSION}/site-packages /usr/local/lib/python${PYTHON_VERSION}/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${PORT}", "--workers", "${WORKERS}", "--root-path", "${API_ROOT_PATH}"]
