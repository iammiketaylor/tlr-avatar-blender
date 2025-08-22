# main.py
import base64
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse

app = FastAPI(title="Blender Render API")

BLENDER_BIN_CANDIDATES = ["blender", "/usr/bin/blender", "/usr/local/bin/blender"]
PNG_PATH = "/tmp/blender_test.png"


@app.get("/", response_class=PlainTextResponse)
def root():
    # Render hits GET / for health. Return 200 and point humans at the useful endpoints.
    return "ok – try /healthz, /blender/check, /render/test, or /render/test.png"


def find_blender() -> str:
    for p in BLENDER_BIN_CANDIDATES:
        try:
            r = subprocess.run([p, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if r.returncode == 0:
                return p
        except Exception:
            pass
    raise HTTPException(status_code=500, detail="Blender binary not found in container.")


def build_blender_script(out_path: str, samples: int = 32) -> str:
    return f"""
import bpy
import mathutils

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = {samples}
try:
    scene.display_settings.display_device = 'sRGB'
    scene.view_settings.view_transform = 'Standard'
except Exception:
    pass

if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
wn = scene.world.node_tree
wn.nodes.clear()
n_bg = wn.nodes.new('ShaderNodeBackground')
n_bg.inputs[0].default_value = (0.02, 0.02, 0.03, 1.0)
n_bg.inputs[1].default_value = 1.0
n_out = wn.nodes.new('ShaderNodeOutputWorld')
wn.links.new(n_bg.outputs['Background'], n_out.inputs['Surface'])

bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0))
plane = bpy.context.object
m_plane = bpy.data.materials.new("PlaneMat")
m_plane.use_nodes = True
p_bsdf = m_plane.node_tree.nodes.get("Principled BSDF")
p_bsdf.inputs["Base Color"].default_value = (0.2, 0.2, 0.22, 1.0)
p_bsdf.inputs["Roughness"].default_value = 1.0
plane.data.materials.append(m_plane)

bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1.0))
sphere = bpy.context.object
m_emit = bpy.data.materials.new("EmitMat")
m_emit.use_nodes = True
nodes = m_emit.node_tree.nodes
for n in list(nodes):
    if n.type != 'OUTPUT_MATERIAL':
        nodes.remove(n)
n_em = nodes.new('ShaderNodeEmission')
n_em.inputs['Color'].default_value = (1.0, 0.5, 0.1, 1.0)
n_em.inputs['Strength'].default_value = 5.0
n_outm = nodes['Material Output']
m_emit.node_tree.links.new(n_em.outputs['Emission'], n_outm.inputs['Surface'])
sphere.data.materials.append(m_emit)

bpy.ops.object.light_add(type='AREA', location=(2, -2, 3))
light = bpy.context.object
light.data.energy = 3000.0
light.data.size = 2.0

bpy.ops.object.camera_add(location=(3, -3, 2))
cam = bpy.context.object
scene.camera = cam

def look_at(obj, target):
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

look_at(cam, (0, 0, 1.0))

scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = r'{out_path}'

bpy.ops.render.render(write_still=True)
print("Saved:", scene.render.filepath)
"""


def run_blender_and_get_png(samples: int = 32, timeout_s: int = 480):
    blender = find_blender()
    Path(PNG_PATH).unlink(missing_ok=True)

    script = build_blender_script(PNG_PATH, samples=samples)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(script)
        tf_path = tf.name

    try:
        proc = subprocess.run(
            [blender, "-b", "-noaudio", "-P", tf_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
            text=True,
        )
    finally:
        try:
            os.remove(tf_path)
        except Exception:
            pass

    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"Blender failed (rc={proc.returncode}). See logs.")

    if not Path(PNG_PATH).exists():
        raise HTTPException(status_code=500, detail="PNG not written (expected at /tmp/blender_test.png).")

    data = Path(PNG_PATH).read_bytes()
    return data, proc.stdout, proc.stderr


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"


@app.get("/blender/check")
def blender_check():
    blender = find_blender()
    r = subprocess.run([blender, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
    return {"ok": True, "version": r.stdout.splitlines()[0].strip() if r.stdout else "unknown"}


@app.get("/render/test")  # direct PNG download
def render_test(samples: int = 32):
    try:
        data, _, _ = run_blender_and_get_png(samples=samples)
        headers = {"Content-Disposition": 'attachment; filename="blender_test.png"'}
        return StreamingResponse(iter([data]), media_type="image/png", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/render/test.png")  # JSON with base64 + logs
def render_test_json(samples: int = 32):
    try:
        data, stdout, stderr = run_blender_and_get_png(samples=samples)
        b64 = base64.b64encode(data).decode("ascii")
        return JSONResponse(
            {
                "ok": True,
                "engine": "CYCLES-CPU",
                "samples": samples,
                "timeout_s": 480,
                "png": "data:image/png;base64," + b64,
                "stdout": stdout,
                "stderr": stderr,
            }
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Convenience aliases if you bookmarked earlier names
@app.get("/render/test-raw")
def render_test_raw_alias(samples: int = 32):
    return render_test(samples=samples)


@app.get("/render/test.raw.png")
def render_test_dotraw_alias(samples: int = 32):
    return render_test(samples=samples)
