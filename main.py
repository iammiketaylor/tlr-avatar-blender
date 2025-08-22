# /app/main.py  — FastAPI service (no Flask)
import os
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(title="tlr-avatar", version="1.0.0")


@app.get("/")
def root():
    return {"service": "tlr-avatar", "version": "1.0.0"}


@app.get("/ok")
def ok():
    return {"ok": True}


# Render health check — matches Settings -> Health Check Path
@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


def _find_blender() -> str:
    candidates = [
        shutil.which("blender"),
        "/usr/bin/blender",
        "/opt/blender/blender",
        "/usr/local/bin/blender",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return ""


@app.get("/blender/check")
def blender_check():
    path = _find_blender()
    return {"has_blender": bool(path), "blender_path": path}


@app.get("/blender/version")
def blender_version():
    path = _find_blender()
    if not path:
        return {"ok": False, "stdout": "", "stderr": "blender not found"}
    try:
        cp = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=10)
        return {
            "ok": cp.returncode == 0,
            "rc": cp.returncode,
            "stdout": (cp.stdout or "")[-4000:],
            "stderr": (cp.stderr or "")[-4000:],
        }
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}
