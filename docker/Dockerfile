# Use a slim Python image for a smaller footprint
FROM python:3.12-slim

# Set environment variables
# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install system dependencies
# git is required for installing the SDK from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
# Note: .dockerignore should exclude unnecessary files
COPY . .

# Ensure the start script is executable
RUN chmod +x start_server.sh

# Create a non-root user and switch to it for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Expose the default port
EXPOSE 8000

# Set the entrypoint to the start script
# Default environment variables can be overridden at runtime
ENTRYPOINT ["./start_server.sh"]
