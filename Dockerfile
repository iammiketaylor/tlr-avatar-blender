# Dockerfile  blender with required runtime libs
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages including Blender and all shared libs Blender needs at runtime
RUN apt-get update && apt-get install -y \
    blender \
    python3 python3-pip \
    curl ca-certificates unzip \
    libxkbcommon0 libxkbcommon-x11-0 \
    libxrender1 libxext6 libxi6 libxfixes3 libxrandr2 \
    libgl1 libegl1 libsm6 libx11-6 libx11-xcb1 libxcb1 \
    libdbus-1-3 libfontconfig1 libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# App deps
WORKDIR /app
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# App code
COPY main.py /app/
COPY render_avatar.py /app/

# Default start
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
