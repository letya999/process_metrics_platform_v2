FROM python:3.11-slim

# Create non-root user
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# Copy requirements and install
COPY requirements.txt ./
RUN python -m venv .venv && .venv/bin/pip install --upgrade pip setuptools wheel && .venv/bin/pip install -r requirements.txt

# Copy application code
COPY app ./app

# Switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=40s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
