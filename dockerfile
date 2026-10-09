# Use official Python runtime as base
FROM python:3.10-slim

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Use official Python runtime as base
FROM python:3.10-slim

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy repository files
COPY . .

# Download offline web assets (React, Tailwind) if not committed
RUN python scripts/setup_vendor.py

# Generate initial incident data files so data exists upon startup
RUN python generate_data.py --scenario festival_deadlock --seed 42 --out data

# Expose default port
EXPOSE 8000

# Bind Uvicorn to Render's dynamically provided $PORT variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}

RUN python scripts/setup_vendor.py || true
RUN python generate_data.py --scenario festival_deadlock --seed 42 --out data || true
