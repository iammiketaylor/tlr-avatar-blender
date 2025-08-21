FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Base OS deps
RUN apt-get update && apt-get install -y \
    wget curl xz-utils ca-certificates python3 python3-pip unzip \
    libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libx11-6 libgl1 \
 && rm -rf /var/lib/apt/lists/*

# Blender 3.6 LTS
RUN wget -q https://mirror.clarkson.edu/blender/release/Blender3.6/blender-3.6.13-linux-x64.tar.xz \
 && tar -xJf blender-3.6.13-linux-x64.tar.xz -C /opt \
 && mv /opt/blender-3.6.13-linux-x64 /opt/blender \
 && rm blender-3.6.13-linux-x64.tar.xz
ENV PATH="/opt/blender:${PATH}"

# Fetch MB-Lab from a maintained fork at build time (no GitHub auth)
# Try codeload main, codeload master, archive main.zip, archive master.zip
RUN set -eux; \
  urls="\
    https://codeload.github.com/animate1978/MB-Lab/zip/refs/heads/main \
    https://codeload.github.com/animate1978/MB-Lab/zip/refs/heads/master \
    https://github.com/animate1978/MB-Lab/archive/refs/heads/main.zip \
    https://github.com/animate1978/MB-Lab/archive/refs/heads/master.zip \
  "; \
  ok=""; \
  for u in $urls; do \
    echo "Trying $u"; \
    if curl -fSL "$u" -o /tmp/MB-Lab.zip; then ok=1; break; fi; \
  done; \
  if [ -z "$ok" ]; then echo "Failed to download MB-Lab ZIP from all sources"; exit 1; fi; \
  unzip -q /tmp/MB-Lab.zip -d /opt; \
  MB_DIR="$(ls -d /opt/MB-Lab-* 2>/dev/null | head -n 1)"; \
  if [ -z "$MB_DIR" ]; then echo "Unzip succeeded but MB-Lab directory not found"; exit 1; fi; \
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
