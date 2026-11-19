FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install DuckDB httpfs extension during image build
RUN python3 -c "import duckdb; conn = duckdb.connect(':memory:'); conn.execute('INSTALL httpfs;')"

COPY app/ ./app/

ENV PYTHONPATH=/app
ENV S3_ENDPOINT=minio:9000
ENV MINIO_ROOT_USER=bakeryadmin
ENV MINIO_ROOT_PASSWORD=bakerydemo123
ENV GOLD_BUCKET=bakery-gold

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
