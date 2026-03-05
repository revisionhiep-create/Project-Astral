FROM python:3.11-slim

# Set timezone to Pacific for correct time reporting
ENV TZ=America/Los_Angeles

WORKDIR /app

# Install system dependencies for voice support, git for pip, and patch
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libopus0 \
    git \
    patch \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Apply OpusError fix patch
COPY fix-OpusError.patch /tmp/
RUN cd /usr/local/lib/python3.11/site-packages && patch -p1 < /tmp/fix-OpusError.patch

# Copy bot code
COPY . .

# Run bot
CMD ["python", "main.py"]
