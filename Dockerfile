FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Base OS deps
RUN apt-get update && apt-get install -y \
    wget xz-utils ca-certificates python3 python3-pip unzip \
    libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libx11-6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

# Blender 3.6 LTS
RUN wget -q https://mirror.clarkson.edu/blender/release/Blender3.6/blender-3.6.13-linux-x64.tar.xz \
    && tar -xJf blender-3.6.13-linux-x64.tar.xz -C /opt \
    && mv /opt/blender-3.6.13-linux-x64 /opt/blender \
    && rm blender-3.6.13-linux-x64.tar.xz
ENV PATH="/opt/blender:${PATH}"

# MB‑Lab add-on (download at build time; try main then master; use codeload fallback style)
RUN set -eux; \
    found=; \
    for BR in main master; do \
      for HOST in github.com/codeload.github.com; do \
        URL="https://$HOST/animate1978/MB-Lab/zip/refs/heads/$BR"; \
        echo "Trying $URL"; \
        if wget -q -O /tmp/MB-Lab.zip "$URL"; then found=1; break; fi; \
      done; \
      if [ "$found" = "1" ]; then break; fi; \
    done; \
    if [ -z "$found" ]; then echo "Failed to fetch MB-Lab zip"; exit 1; fi; \
    unzip -q /tmp/MB-Lab.zip -d /opt; \
    MB_DIR=$(ls -d /opt/MB-Lab-* | head -n 1); \
    mv "$MB_DIR" /opt/MB-Lab; \
    mkdir -p /root/.config/blender/3.6/scripts/addons; \
    cp -r /opt/MB-Lab /root/.config/blender/3.6/scripts/addons/MB-Lab

WORKDIR /app

# Python deps
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# App code
COPY main.py /app/
COPY render_avatar.py /app/

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
