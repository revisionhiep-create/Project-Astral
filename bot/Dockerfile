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
COPY Project-Astral/bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Apply OpusError fix patch
COPY Project-Astral/bot/fix-OpusError.patch /tmp/
RUN cd /usr/local/lib/python3.11/site-packages && patch -p1 < /tmp/fix-OpusError.patch

# Apply DAVE E2EE decryption patch for voice receive
COPY Project-Astral/bot/patches/apply_dave_patch.sh /tmp/
RUN chmod +x /tmp/apply_dave_patch.sh && /tmp/apply_dave_patch.sh

# Copy shared_memory module from parent directory
COPY shared_memory /app/shared_memory

# Copy bot code
COPY Project-Astral/bot .

# Run bot
CMD ["python", "main.py"]
