# main.py  — drop-in Flask app that renders a bright PNG via Blender headless
import os, base64, tempfile, subprocess, textwrap, time
from pathlib import Path
from flask import Flask, jsonify, Response, request

app = Flask(__name__)

SERVICE_NAME = "tlr-avatar"
SERVICE_VERSION = "1.0.0"

def find_blender():
    candidates = [
        os.environ.get("BLENDER_PATH"),
        "/usr/bin/blender",
        "/opt/blender/blender",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None

BLENDER_PATH = find_blender()

def run_blender_job(job_py: str):
    """Run a small Blender job in headless mode and return dict with png/rc/out."""
    tmpdir = Path(tempfile.mkdtemp(prefix="bl_job_"))
    job_path = tmpdir / "job.py"
    out_path = tmpdir / "out.png"

    # write the job script
    job_path.write_text(job_py)

    # pick blender
    if not BLENDER_PATH:
        return dict(ok=False, rc=127, png=b"", stdout="", stderr="Blender not found")

    env = os.environ.copy()
    env["PNG_OUT"] = str(out_path)

    # run blender headless
    cmd = [
        BLENDER_PATH,
        "-noaudio",
        "-b",               # background (no window)
        "-P", str(job_path) # run python script
    ]
    proc = subprocess.run(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    stdout = proc.stdout
    stderr = proc.stderr
    rc = proc.returncode

    png_bytes = out_path.read_bytes() if out_path.exists() else b""
    return dict(ok=(rc == 0 and len(png_bytes) > 0), rc=rc, png=png_bytes, stdout=stdout, stderr=stderr)

BRIGHT_SPHERE_JOB = textwrap.dedent(r"""
import bpy, bmesh, os
from math import radians
from mathutils import Vector

# Reset to empty factory scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# Use Eevee and a standard view so we don't depend on Filmic
scene.render.engine = 'BLENDER_EEVEE'
scene.view_settings.view_transform = 'Standard'

# Make world bright white (so nothing is black even without lights)
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
wn = scene.world.node_tree
for n in list(wn.nodes):
    wn.nodes.remove(n)
bg = wn.nodes.new('ShaderNodeBackground')
bg.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
bg.inputs['Strength'].default_value = 1.0
out = wn.nodes.new('ShaderNodeOutputWorld')
wn.links.new(bg.outputs['Background'], out.inputs['Surface'])

# Add a simple sphere with an emission material (guaranteed to be visible)
mesh = bpy.data.meshes.new("BodyMesh")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.6)
bm.to_mesh(mesh); bm.free()
obj = bpy.data.objects.new("Body", mesh)
bpy.context.collection.objects.link(obj)

mat = bpy.data.materials.new("EmissiveMat")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
em = nt.nodes.new('ShaderNodeEmission')
em.inputs['Color'].default_value = (0.12, 0.40, 0.80, 1.0)
em.inputs['Strength'].default_value = 3.0
mout = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(em.outputs['Emission'], mout.inputs['Surface'])
obj.data.materials.append(mat)

# Add a light (EeVee likes one, even though we have emission)
sun_data = bpy.data.lights.new(name="Sun", type='SUN')
sun = bpy.data.objects.new(name="Sun", object_data=sun_data)
bpy.context.collection.objects.link(sun)
sun.location = (0.0, -2.0, 5.0)
sun.data.energy = 3.0

# Camera looking at origin
cam_data = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (0.0, -3.0, 1.5)
cam.rotation_euler = (radians(15), 0.0, 0.0)
scene.camera = cam

# Render settings
scene.render.resolution_x = 800
scene.render.resolution_y = 800
scene.render.film_transparent = False

# Render to the path Blender was given via env
out_path = os.environ.get("PNG_OUT", "/tmp/out.png")
bpy.ops.render.render(write_still=False)
bpy.data.images['Render Result'].save_render(out_path)
""").strip()

@app.get("/")
def root():
    return jsonify(dict(service=SERVICE_NAME, version=SERVICE_VERSION))

@app.get("/blender/check")
def blender_check():
    return jsonify(dict(has_blender=bool(BLENDER_PATH), blender_path=BLENDER_PATH or ""))

@app.get("/blender/smoke")
def blender_smoke():
    """Return a JSON payload with base64 PNG (or raw PNG if ?as=png)."""
    res = run_blender_job(BRIGHT_SPHERE_JOB)

    # If the caller wants raw PNG bytes (for <img src>), serve it directly
    if request.args.get("as") == "png" and res["ok"]:
        return Response(res["png"], mimetype="image/png",
                        headers={"Cache-Control": "no-store"})
    # Otherwise, return JSON with data URL (or errors)
    b64 = base64.b64encode(res["png"]).decode("ascii") if res["png"] else ""
    return jsonify(dict(
        ok=res["ok"],
        rc=res["rc"],
        stdout=res["stdout"],
        stderr=res["stderr"],
        png=("data:image/png;base64," + b64) if b64 else ""
    ))

@app.get("/blender/smoke_view")
def blender_smoke_view():
    """Server-side render & inline the PNG so adblockers/caching can’t hide it."""
    res = run_blender_job(BRIGHT_SPHERE_JOB)
    if res["ok"]:
        b64 = base64.b64encode(res["png"]).decode("ascii")
        body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Blender PNG</title></head>
<body style="margin:0;background:#fff;">
  <img alt="render" style="display:block;max-width:96vw;height:auto;background:#fff;"
       src="data:image/png;base64,{b64}">
  <pre style="white-space:pre-wrap;padding:12px;background:#fff;color:#333;border-top:1px solid #ddd">
rc={res["rc"]}</pre>
</body></html>"""
    else:
        # Show errors plainly
        body = f"""<!doctype html><html><body style="font:14px/1.4 system-ui;white-space:pre-wrap">
<h3>Render failed</h3>
<code>rc={res["rc"]}</code>
<h4>stderr</h4><pre>{res["stderr"]}</pre>
<h4>stdout</h4><pre>{res["stdout"]}</pre>
</body></html>"""
    return Response(body, mimetype="text/html", headers={"Cache-Control": "no-store"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
