# /app/main.py  — FastAPI service with a Blender test render (Cycles CPU, headless)

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, Response

app = FastAPI(title="tlr-avatar", version="1.0.1")


@app.get("/")
def root():
    return {"service": "tlr-avatar", "version": "1.0.1"}


@app.get("/ok")
def ok():
    return {"ok": True}


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
        cp = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=30)
        return {
            "ok": cp.returncode == 0,
            "rc": cp.returncode,
            "stdout": (cp.stdout or "")[-4000:],
            "stderr": (cp.stderr or "")[-4000:],
        }
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def _run_blender_headless(out_png: Path) -> dict:
    """Render a simple scene to out_png using Cycles CPU (no display needed)."""
    blender = _find_blender()
    if not blender:
        return {"ok": False, "error": "blender not found", "stdout": "", "stderr": ""}

    tmpdir = Path(tempfile.mkdtemp(prefix="bljob_"))
    job_py = tmpdir / "job.py"

    # Blender background script
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
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.cycles.device = 'CPU'  # force CPU; avoids GL/display issues in headless

scene.render.filepath = r"{str(out_png)}"
bpy.ops.render.render(write_still=True)
"""

    job_py.write_text(script, encoding="utf-8")

    cp = subprocess.run(
        [blender, "-b", "-noaudio", "-P", str(job_py)],
        capture_output=True,
        text=True,
        timeout=180,
    )

    return {
        "ok": cp.returncode == 0 and out_png.exists(),
        "rc": cp.returncode,
        "stdout": (cp.stdout or "")[-6000:],
        "stderr": (cp.stderr or "")[-6000:],
        "png_path": str(out_png) if out_png.exists() else "",
    }


@app.get("/render/test.png")
def render_test_png_json():
    """Returns JSON with a data: URL for the PNG + logs (easy to debug)."""
    out_png = Path("/tmp/blender_test.png")
    if out_png.exists():
        try:
            out_png.unlink()
        except Exception:
            pass

    res = _run_blender_headless(out_png)
    if not res["ok"]:
        return JSONResponse({"ok": False, **res}, status_code=500)

    data = out_png.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return {
        "ok": True,
        "engine": "CYCLES-CPU",
        "png": f"data:image/png;base64,{b64}",
        "stdout": res["stdout"],
        "stderr": res["stderr"],
        "rc": res["rc"],
    }


@app.get("/render/test.raw.png")
def render_test_png_raw():
    """Returns the PNG bytes directly (easier to view in browser)."""
    out_png = Path("/tmp/blender_test.png")
    if out_png.exists():
        try:
            out_png.unlink()
        except Exception:
            pass

    res = _run_blender_headless(out_png)
    if not res["ok"]:
        return JSONResponse({"ok": False, **res}, status_code=500)

    return Response(content=out_png.read_bytes(), media_type="image/png")
