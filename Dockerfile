# BuddyHelps Voice AI Server
# RunPod RTX A5000 deployment

FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY scripts/ ./scripts/

# Expose port
EXPOSE 8000

# Warmup and run
CMD ["sh", "-c", "python scripts/warmup.py && python -m src.main"]
