# Use an official Python runtime as the base image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install the required packages
RUN pip install -r requirements.txt --no-cache-dir

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable
ENV FLASK_APP=run.py

# --max-requests recycles each worker after ~250 requests so the large transient
# allocations from full-catalog M3U/VOD generation are returned to the OS instead
# of ratcheting RSS up forever. --timeout 0 stays for long-lived live-stream proxying.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "0", "--graceful-timeout", "30", "--workers", "3", "--keep-alive", "10", "--max-requests", "250", "--max-requests-jitter", "50", "run:app"]