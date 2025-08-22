# main.py
import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

APP_PORT = int(os.getenv("PORT", "10000"))
TEST_PNG_PATH = Path("/tmp/blender_test.png")

app = FastAPI(title="tlr-avatar-blender", version="1.1.0")


# ---------- helpers ----------

def _run(cmd: List[str], timeout: int = 480) -> Tuple[int, str, str]:
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
    return (out or err).strip()


def _blender_test_script(out_png: Path, samples: int) -> str:
    """
    A tiny Blender script that creates a guaranteed-not-black scene and renders to out_png.
    - World background > 0
    - Sun + Point lights
    - Emissive sphere
    - Camera aimed at sphere
    """
    return f"""
import bpy
from mathutils import Vector

# Reset to empty scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ---- color management (headless fallback safe)
try:
    scene.view_settings.view_transform = 'Standard'
    scene.display_settings.display_device = 'sRGB'
except Exception:
    pass

# ---- world: medium-dark ambient so it's not pitch black
world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs[0].default_value = (0.20, 0.20, 0.20, 1.0)  # mid-dark grey
    bg.inputs[1].default_value = 1.0

# ---- camera
cam = bpy.data.cameras.new("Cam")
cam_obj = bpy.data.objects.new("Cam", cam)
bpy.context.scene.collection.objects.link(cam_obj)
cam_obj.location = (3.0, -3.0, 2.0)

# ---- objects: sphere (emissive) and ground plane
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0.0, 0.0, 1.0))
sphere = bpy.context.active_object
bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 0.0, 0.0))

# Make sphere emissive so it shows up even if lights fail
mat = bpy.data.materials.new("MatEmission")
mat.use_nodes = True
nodes = mat.node_tree.nodes
for n in list(nodes):
    nodes.remove(n)
out_node = nodes.new("ShaderNodeOutputMaterial")
em_node = nodes.new("ShaderNodeEmission")
em_node.inputs["Color"].default_value = (0.9, 0.4, 0.2, 1.0)
em_node.inputs["Strength"].default_value = 5.0
mat.node_tree.links.new(em_node.outputs["Emission"], out_node.inputs["Surface"])
sphere.data.materials.clear()
sphere.data.materials.append(mat)

# ---- aim camera at sphere
def look_at(obj, target_vec):
    direction = (Vector(target_vec) - obj.location).normalized()
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
look_at(cam_obj, sphere.location)

# ---- lights: sun + point
sun = bpy.data.lights.new(name="Sun", type='SUN')
sun.energy = 3.0
sun_obj = bpy.data.objects.new(name="Sun", object_data=sun)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.location = (4.0, -4.0, 6.0)
sun_obj.rotation_euler = (0.8, 0.0, 0.8)

pt = bpy.data.lights.new(name="KeyPoint", type='POINT')
pt.energy = 2000.0
pt_obj = bpy.data.objects.new(name="KeyPoint", object_data=pt)
bpy.context.scene.collection.objects.link(pt_obj)
pt_obj.location = (1.5, -1.5, 2.5)

# ---- render settings (Cycles CPU)
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = int({samples})
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.resolution_percentage = 100
scene.camera = cam_obj

# output
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = r"{str(out_png)}"
bpy.ops.render.render(write_still=True)
"""


def _render_test_png(out_png: Path, samples: int = 8, timeout: int = 480) -> Tuple[str, str]:
    """
    Write a tiny blender script to a temp file, run blender headless to render out_png.
    Returns (stdout, stderr). Raises if Blender fails.
    """
    out_png.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_png.unlink(missing_ok=True)
    except Exception:
        pass

    script_text = _blender_test_script(out_png, samples)

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(script_text)
        tf.flush()
        script_path = tf.name

    try:
        rc, out, err = _run(["blender", "-b", "-noaudio", "-P", script_path], timeout=timeout)
    finally:
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
    return "tlr-avatar-blender is running. Try /healthz, /blender/check, /render/test (file), or /render/test.png (JSON+b64)."


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


# --- render: file (multiple aliases so it's easy to hit)

def _file_response_or_500() -> FileResponse:
    try:
        _render_test_png(TEST_PNG_PATH, samples=8, timeout=480)
        return FileResponse(str(TEST_PNG_PATH), media_type="image/png", filename="blender_test.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/render/test.raw.png")
def render_test_raw_png():
    return _file_response_or_500()

@app.get("/render/test-raw")
def render_test_raw_alias1():
    return _file_response_or_500()

@app.get("/render/test")
def render_test_raw_alias2():
    return _file_response_or_500()


# --- render: JSON with base64 and logs

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
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=False)
