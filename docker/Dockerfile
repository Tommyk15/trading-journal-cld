# Multi-stage build for production
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Development stage
FROM base as development

# Install development dependencies
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

# Copy source code
COPY . .

# Install package in editable mode
RUN pip install -e .

# Expose port
EXPOSE 8000

# Run development server
CMD ["uvicorn", "trading_journal.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base as production

# Copy requirements and install
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY src/ /app/src/
COPY pyproject.toml /app/

# Install package
RUN pip install .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run production server
CMD ["uvicorn", "trading_journal.main:app", "--host", "0.0.0.0", "--port", "8000"]
