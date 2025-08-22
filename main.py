# /app/main.py — FastAPI + headless Blender test with robust error handling

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, Response

APP_VERSION = "1.0.2"
BLENDER_TIMEOUT = int(os.getenv("RENDER_TIMEOUT", "480"))  # give Blender more time for first run
SAMPLES = int(os.getenv("CYCLES_SAMPLES", "8"))            # keep it fast for smoke test

app = FastAPI(title="tlr-avatar", version=APP_VERSION)


# ------------------------------
# tiny helpers
# ------------------------------
def _find_blender() -> str:
    cands = [
        shutil.which("blender"),
        "/usr/bin/blender",
        "/opt/blender/blender",
        "/usr/local/bin/blender",
    ]
    for p in cands:
        if p and os.path.exists(p):
            return p
    return ""


def _json_err(msg: str, **extra):
    payload = {"ok": False, "error": msg}
    payload.update(extra)
    return JSONResponse(payload, status_code=500)


# ------------------------------
# basic health
# ------------------------------
@app.get("/")
def root():
    return {"service": "tlr-avatar", "version": APP_VERSION}


@app.get("/ok")
def ok():
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/diag")
def diag():
    try:
        return {
            "ok": True,
            "version": APP_VERSION,
            "env": {
                "PORT": os.getenv("PORT"),
                "RENDER_TIMEOUT": os.getenv("RENDER_TIMEOUT"),
                "CYCLES_SAMPLES": os.getenv("CYCLES_SAMPLES"),
            },
            "blender_path": _find_blender(),
            "cwd": str(Path.cwd()),
            "files_in_app": sorted([p.name for p in Path("/app").glob("*")]),
        }
    except Exception as e:
        return _json_err(f"diag failed: {e}")


# ------------------------------
# blender checks
# ------------------------------
@app.get("/blender/check")
def blender_check():
    path = _find_blender()
    return {"ok": bool(path), "has_blender": bool(path), "blender_path": path}


@app.get("/blender/version")
def blender_version():
    path = _find_blender()
    if not path:
        return _json_err("blender not found")
    try:
        cp = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=30)
        return {
            "ok": cp.returncode == 0,
            "rc": cp.returncode,
            "stdout": (cp.stdout or "")[-4000:],
            "stderr": (cp.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired:
        return _json_err("blender -v timed out")
    except Exception as e:
        return _json_err(f"blender -v error: {e}")


# ------------------------------
# render job
# ------------------------------
def _run_blender_headless(out_png: Path) -> Dict[str, Any]:
    """Render a trivial Cycles CPU scene to out_png and return logs."""
    blender = _find_blender()
    if not blender:
        return {"ok": False, "error": "blender not found", "stdout": "", "stderr": ""}

    tmpdir = Path(tempfile.mkdtemp(prefix="bljob_"))
    job_py = tmpdir / "job.py"

    # Keep it dead simple + CPU-only + low samples
    script = f"""
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)

# camera
cam = bpy.data.cameras.new("Cam")
cam_obj = bpy.data.objects.new("Cam", cam)
bpy.context.scene.collection.objects.link(cam_obj)
cam_obj.location = (0, -3.0, 1.5)
cam_obj.rotation_euler = (1.1, 0.0, 0.0)
bpy.context.scene.camera = cam_obj

# light
light_data = bpy.data.lights.new(name="Light", type='SUN')
light_obj = bpy.data.objects.new(name="Light", object_data=light_data)
bpy.context.scene.collection.objects.link(light_obj)
light_obj.location = (4, -4, 6)

# sphere + ground
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0,0,1))
bpy.ops.mesh.primitive_plane_add(size=6, location=(0,0,0))

# render settings
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = {SAMPLES}
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100

scene.render.filepath = r"{str(out_png)}"
bpy.ops.render.render(write_still=True)
"""

    job_py.write_text(script, encoding="utf-8")

    try:
        cp = subprocess.run(
            [blender, "-b", "-noaudio", "-P", str(job_py)],
            capture_output=True,
            text=True,
            timeout=BLENDER_TIMEOUT,
        )
        return {
            "ok": cp.returncode == 0 and out_png.exists(),
            "rc": cp.returncode,
            "stdout": (cp.stdout or "")[-12000:],
            "stderr": (cp.stderr or "")[-12000:],
            "png_path": str(out_png) if out_png.exists() else "",
        }
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "error": f"timeout after {BLENDER_TIMEOUT}s", "stdout": (e.stdout or ""), "stderr": (e.stderr or "")}
    except Exception as e:
        return {"ok": False, "error": f"subprocess error: {e}", "stdout": "", "stderr": ""}


@app.get("/render/test.png")
def render_test_png_json():
    """JSON with base64 PNG + run logs (safe: never throws 500)."""
    try:
        out_png = Path("/tmp/blender_test.png")
        if out_png.exists():
            try:
                out_png.unlink()
            except Exception:
                pass

        res = _run_blender_headless(out_png)
        if not res.get("ok"):
            return _json_err("render failed", **res)

        data = out_png.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return {
            "ok": True,
            "engine": "CYCLES-CPU",
            "samples": SAMPLES,
            "timeout_s": BLENDER_TIMEOUT,
            "png": f"data:image/png;base64,{b64}",
            "stdout": res.get("stdout", ""),
            "stderr": res.get("stderr", ""),
            "rc": res.get("rc"),
        }
    except Exception as e:
        return _json_err(f"handler error: {e}")


@app.get("/render/test.raw.png")
def render_test_png_raw():
    """PNG bytes directly; on error, returns JSON (not a 500 page)."""
    try:
        out_png = Path("/tmp/blender_test.png")
        if out_png.exists():
            try:
                out_png.unlink()
            except Exception:
                pass

        res = _run_blender_headless(out_png)
        if not res.get("ok"):
            return _json_err("render failed", **res)

        return Response(content=out_png.read_bytes(), media_type="image/png")
    except Exception as e:
        return _json_err(f"handler error: {e}")
