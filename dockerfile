# Use official Python runtime as base
FROM python:3.10-slim

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies (if needed) and python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy repository content
COPY . .

# Generate initial incident data so the engine has data files upon startup
RUN python generate_data.py --scenario festival_deadlock --seed 42 --out data

# Expose port (default fallback 8000)
EXPOSE 8000

# Start Uvicorn using shell form to dynamically bind to Railway's $PORT
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}