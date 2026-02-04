FROM python:3.11-slim

# Set timezone to Pacific for correct time reporting
ENV TZ=America/Los_Angeles

WORKDIR /app

# Install system dependencies for voice support
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Run bot
CMD ["python", "main.py"]
