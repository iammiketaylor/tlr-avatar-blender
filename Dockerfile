FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# System deps incl. Blender (headless) and Python
RUN apt-get update && apt-get install -y \
  blender \
  python3 python3-pip python3-venv \
  curl ca-certificates unzip \
  libxkbcommon0 libxkbcommon-x11-0 \
  libxrender1 libxext6 libxi6 libxfixes3 libxrandr2 \
  libgl1 libegl1 libsm6 libx11-6 libx11-xcb1 libxcb1 \
  libdbus-1-3 libfontconfig1 libfreetype6 \
  && rm -rf /var/lib/apt/lists/*

# App dir
WORKDIR /app

# --- IMPORTANT: copy requirements before install so Docker rebuilds this layer when reqs change
COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir -r /app/requirements.txt

# App code
COPY main.py /app/main.py
COPY render_avatar.py /app/render_avatar.py

# Headless-safe envs
ENV PYTHONUNBUFFERED=1 \
    BLENDER_USER_CONFIG=/tmp \
    BLENDER_USER_SCRIPTS=/tmp

# Render will provide $PORT. Default to 10000 for local sanity.
ENV PORT=10000
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
