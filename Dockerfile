FROM python:3.11-slim

WORKDIR /app

# Non-root user
RUN adduser --disabled-password --no-create-home botuser

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY . .

# Logs directory
RUN mkdir -p logs && chown -R botuser:botuser /app

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080')" || exit 1

EXPOSE 8080

CMD ["python", "main.py"]
