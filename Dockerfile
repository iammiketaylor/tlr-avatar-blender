FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Base OS deps
RUN apt-get update && apt-get install -y \
    wget xz-utils ca-certificates python3 python3-pip git unzip \
    libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libx11-6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Blender 3.6 LTS
RUN wget -q https://mirror.clarkson.edu/blender/release/Blender3.6/blender-3.6.13-linux-x64.tar.xz \
    && tar -xJf blender-3.6.13-linux-x64.tar.xz -C /opt \
    && mv /opt/blender-3.6.13-linux-x64 /opt/blender \
    && rm blender-3.6.13-linux-x64.tar.xz
ENV PATH="/opt/blender:${PATH}"

# MB-Lab add-on (download zip instead of git clone for anonymous builds)
RUN wget -q https://codeload.github.com/MB-Lab/MB-Lab/zip/refs/heads/master -O /tmp/MB-Lab.zip \
    && unzip -q /tmp/MB-Lab.zip -d /opt \
    && mv /opt/MB-Lab-master /opt/MB-Lab \
    && mkdir -p /root/.config/blender/3.6/scripts/addons \
    && cp -r /opt/MB-Lab /root/.config/blender/3.6/scripts/addons/MB-Lab

WORKDIR /app

# Python deps
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# App code
COPY main.py /app/
COPY render_avatar.py /app/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
