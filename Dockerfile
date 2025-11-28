# Stage 1: Dependency resolution
FROM astral/uv:python3.13-bookworm-slim AS uv
WORKDIR /swi
COPY pyproject.toml .
RUN uv pip compile pyproject.toml > requirements.txt

# Stage 2: Build
FROM python:3.13-slim AS builder
WORKDIR /swi
COPY --from=uv /swi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Runtime
FROM python:3.13-slim
WORKDIR /swi

# Create and switch to a non-root user
RUN useradd -m swi
USER swi

# Copy only necessary files from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Environment variables
ENV PORT=8000
ENV WORKERS=4

# Healthcheck
# HEALTHCHECK --interval=30s --timeout=3s \
#     CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose the port
EXPOSE 8085

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085", "--workers", "4"]
