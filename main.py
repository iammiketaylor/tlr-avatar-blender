# main.py
import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

APP_PORT = int(os.getenv("PORT", "10000"))
TEST_PNG_PATH = Path("/tmp/blender_test.png")

app = FastAPI(title="tlr-avatar-blender", version="1.0.0")


# ---------- helpers ----------

def _run(cmd: list[str], timeout: int = 480) -> Tuple[int, str, str]:
    """Run a shell command and return (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", e.stderr or "timeout"


def _blender_version() -> str:
    rc, out, err = _run(["blender", "-v"], timeout=30)
    if rc != 0:
        raise RuntimeError(f"blender -v failed: {err or out}")
    # one-line string is fine
    return (out or err).strip()


def _blender_test_script(out_png: Path, samples: int) -> str:
    """
    A tiny Blender script that creates a lit sphere-on-plane,
    points the camera at it, and renders to out_png.
    """
    # NOTE: this script runs *inside* Blender's Python (so we import bpy there).
    return f"""
import bpy
from mathutils import Vector

# Reset to empty scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---- world: dim ambient so it's never pitch black
world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs[0].default_value = (0.05, 0.05, 0.05, 1.0)  # dark grey
    bg.inputs[1].default_value = 1.0

# ---- camera
cam = bpy.data.cameras.new("Cam")
cam_obj = bpy.data.objects.new("Cam", cam)
bpy.context.scene.collection.objects.link(cam_obj)
cam_obj.location = (3.0, -3.0, 2.0)

# ---- objects: sphere and ground plane
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0.0, 0.0, 1.0))
sphere = bpy.context.active_object
bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0.0, 0.0, 0.0))

# ---- aim camera at sphere
def look_at(obj, target_vec):
    direction = (Vector(target_vec) - obj.location).normalized()
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
look_at(cam_obj, sphere.location)

# ---- sun light
sun = bpy.data.lights.new(name="Sun", type='SUN')
sun.energy = 5.0
sun_obj = bpy.data.objects.new(name="Sun", object_data=sun)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (4.0, -4.0, 6.0)
sun_obj.rotation_euler = (0.8, 0.0, 0.8)

# ---- render settings
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = int({samples})
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100

scene.camera = cam_obj
scene.render.filepath = r"{str(out_png)}"
bpy.ops.render.render(write_still=True)
"""


def _render_test_png(out_png: Path, samples: int = 8, timeout: int = 480) -> Tuple[str, str]:
    """
    Write a tiny blender script to a temp file, run blender headless to render out_png.
    Returns (stdout, stderr). Raises if Blender fails.
    """
    # Ensure parent dir exists & remove any stale file
    out_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_png.unlink(missing_ok=True)  # py3.8+: use if exists then unlink
    except Exception:
        pass

    script_text = _blender_test_script(out_png, samples)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(script_text)
        tf.flush()
        script_path = tf.name

    try:
        # Run Blender headless with our script
        rc, out, err = _run(
            ["blender", "-b", "-noaudio", "-P", script_path],
            timeout=timeout,
        )
    finally:
        # Best-effort cleanup of the temporary script
        try:
            Path(script_path).unlink(missing_ok=True)
        except Exception:
            pass

    if rc != 0:
        raise RuntimeError(f"Blender failed (rc={rc}): {err or out}")

    if not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError("Blender reported success but no PNG was written.")

    return out, err


# ---------- routes ----------

@app.get("/", response_class=PlainTextResponse)
def root():
    return "tlr-avatar-blender is running. Try /healthz, /blender/check, /render/test.png, or /render/test.raw.png"


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.get("/ok")
def ok():
    return {"ok": True}


@app.get("/blender/check")
def blender_check():
    try:
        ver = _blender_version()
        return {"ok": True, "version": ver}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/render/test.raw.png")
def render_test_raw_png():
    try:
        _render_test_png(TEST_PNG_PATH, samples=8, timeout=480)
        # Serve the file directly
        return FileResponse(str(TEST_PNG_PATH), media_type="image/png", filename="blender_test.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/render/test.png")
def render_test_png_b64():
    try:
        out, err = _render_test_png(TEST_PNG_PATH, samples=8, timeout=480)
        data = TEST_PNG_PATH.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return JSONResponse(
            {
                "ok": True,
                "engine": "CYCLES-CPU",
                "samples": 8,
                "timeout_s": 480,
                "png": f"data:image/png;base64,{b64}",
                "stdout": out,
                "stderr": err,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)})


# Optional: run directly (Render usually starts with `uvicorn main:app ...`)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=False)
