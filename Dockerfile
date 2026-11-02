# -----------------------------------------------------------------------------
# Dockerfile - recipe for a container image that runs TripMate AI.
# Build:  docker build -t tripmate-ai .
# Run:    docker run --env-file .env -p 8000:8000 tripmate-ai
# The .env file is NOT copied into the image (see .dockerignore); keys are
# passed in at run time with --env-file instead.
# -----------------------------------------------------------------------------

# Start from a small official image that already has Python 3.11.
FROM python:3.11-slim

# All following commands run inside /app in the container.
WORKDIR /app

# Do not write .pyc files, and print logs immediately (no output buffering).
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy only the dependency list first: Docker caches this layer, so the slow
# pip install below re-runs only when requirements.txt changes.
COPY requirements.txt .

# Install the Python packages (--no-cache-dir keeps the image smaller).
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project (minus everything listed in .dockerignore).
COPY . .

# Document that the app listens on port 8000.
EXPOSE 8000

# Start command: uvicorn serves the FastAPI object "app" from app.py.
# 0.0.0.0 = accept connections from outside the container.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
