FROM python:3.11-slim

# Prevent python from writing .pyc files & enable unbuffered streaming logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Step A: Copy dependencies first (optimizes layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step B: Copy application code
COPY . .

# Step C: Create a non-root user for container security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Document that this service listens on 8000
EXPOSE 8000

# Start command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
