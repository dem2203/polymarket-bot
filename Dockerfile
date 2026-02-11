FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Log directory
RUN mkdir -p logs

# Non-root user
RUN useradd -m botuser && chown -R botuser:botuser /app
USER botuser

# Health check
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:8080/ || exit 1

CMD ["python", "main.py"]
