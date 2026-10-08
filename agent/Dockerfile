FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Install system dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY agent/requirements.txt /app/agent/requirements.txt
RUN pip install --no-cache-dir -r /app/agent/requirements.txt

# Copy agent, scenarios, and config
COPY agent/ /app/agent/
COPY scenarios/ /app/scenarios/
COPY mcp/ /app/mcp/

# Default entrypoint: runs the EvoOps Agent investigator loop
CMD ["python", "agent/investigator.py", "--scenario", "downstream_timeout", "--max-steps", "10"]
