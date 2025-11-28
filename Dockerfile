# Stage 1: Build dependencies
FROM python:3.13-slim AS builder

WORKDIR /swi

# Install uv and compile dependencies
RUN pip install uv
COPY pyproject.toml .
RUN uv pip install --system --compile --no-deps -r <(uv pip compile --python-version 3.11 pyproject.toml) && \
    uv pip install --system --editable .

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /swi

# Copy only the necessary files from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Run Uvicorn with multiple workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
