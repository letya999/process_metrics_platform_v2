FROM prefecthq/prefect:2.14-python3.11

USER root
WORKDIR /app

# Install Python deps into image venv
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r /app/requirements.txt

# Copy minimal code layout for Phase 1 (flows will arrive later phases)
COPY . /app

# Default command kept for worker images; overridden by docker-compose when used as worker
CMD ["python", "-c", "import dlt, prefect; print('DLT & Prefect OK')"]
