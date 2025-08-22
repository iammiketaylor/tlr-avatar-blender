# main.py  blender_2  solid CPU render and clear error reporting

from typing import List, Optional, Literal, Dict, Any
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
import base64, json, os, subprocess, tempfile, textwrap, shutil

app = FastAPI(title="TLR Avatar Render Service", version="blender_2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Models ----------

class Viewport(BaseModel):
    width: int = 800
    height: int = 1100
    ortho: bool = True

class Measurements(BaseModel):
    units: Literal["cm", "in"] = "cm"
    height: float
    shoulder_width: Optional[float] = None
    chest: Optional[float] = None
    waist: Optional[float] = None
    hip: Optional[float] = None
    arm_length: Optional[float] = None
    leg_length: Optional[float] = None
    thigh: Optional[float] = None
    calf: Optional[float] = None
    neck: Optional[float] = None

class RenderRequest(BaseModel):
    measurements: Measurements
    pose: str = "POSE01"
    view: Literal["front", "back", "side"] = "front"
    return_: List[Literal["svg", "png"]] = Field(default_factory=lambda: ["svg"], alias="return")
    viewport: Viewport = Viewport()
    engine: Optional[Literal["svg","blender"]] = None  # set to "blender" to force PNG

class RenderResponse(BaseModel):
    svg: str = ""
    png: str = ""
    meta: Dict[str, Any] = {}

# ---------- Simple SVG fallback ----------

def _fallback_svg(w: int, h: int) -> str:
    cx = w / 2.0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white"/>
  <g stroke="#0B2B4A" fill="none" stroke-width="2">
    <ellipse cx="{cx:.1f}" cy="{h*0.12:.1f}" rx="{w*0.07:.1f}" ry="{h*0.06:.1f}"/>
    <line x1="{cx:.1f}" y1="{h*0.18:.1f}" x2="{cx:.1f}" y2="{h*0.85:.1f}"/>
  </g>
</svg>"""

# ---------- Blender helpers ----------

BLENDER_BIN = shutil.which("blender")

def blender_available() -> bool:
    return BLENDER_BIN is not None

def run_blender_job(meas: Dict[str, Any], view: str, vp: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs Blender headless with Cycles CPU and renders a simple mannequin PNG.
    Returns dict: { ok: bool, png: str|"", rc: int, stdout: str, stderr: str }
    """
    if not blender_available():
        return {"ok": False, "png": "", "rc": -1, "stdout": "", "stderr": "blender_not_found"}

    pycode = textwrap.dedent("""
        import bpy, sys, json, math

        def clear_scene():
            bpy.ops.wm.read_homefile(use_empty=True)
            for obj in list(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)

        def add_mannequin():
            # simple parts
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 1.80))  # head
            bpy.ops.mesh.primitive_cylinder_add(radius=0.20, depth=0.60, location=(0, 0, 1.40))  # upper torso
            bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.40, location=(0, 0, 1.00))  # lower torso
            bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.70, location=(-0.25, 0, 1.25))  # arm L
            bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.70, location=( 0.25, 0, 1.25))  # arm R
            bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.00, location=(-0.12, 0, 0.40))  # leg L
            bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.00, location=( 0.12, 0, 0.40))  # leg R

        def scale_to_height(target_m):
            # estimate current height by bounding box of all meshes
            meshes = [o for o in bpy.data.objects if o.type == "MESH"]
            if not meshes:
                return
            zmin, zmax = None, None
            for o in meshes:
                o.select_set(True)
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
                for v in o.bound_box:
                    z = o.matrix_world @ bpy.mathutils.Vector(v)
                o.select_set(False)
            # use scene bounds
            deps = bpy.context.evaluated_depsgraph_get()
            zmin, zmax = 1e9, -1e9
            for o in meshes:
                bb = o.evaluated_get(deps).bound_box
                for v in bb:
                    world_v = o.matrix_world @ bpy.mathutils.Vector((v[0],v[1],v[2]))
                    zmin = min(zmin, world_v.z)
                    zmax = max(zmax, world_v.z)
            cur_h = max(0.01, zmax - zmin)
            scale = target_m / cur_h
            for o in meshes:
                o.scale *= scale

        def add_camera_front_ortho(ortho_scale=2.2):
            cam = bpy.data.cameras.new("cam")
            cam.type = 'ORTHO'
            cam.ortho_scale = ortho_scale
            cam_obj = bpy.data.objects.new("cam", cam)
            bpy.context.scene.collection.objects.link(cam_obj)
            # place in front and point to origin with Track To
            cam_obj.location = (0, 3.0, 1.2)  # y positive, looking -Y
            empty = bpy.data.objects.new("target", None)
            bpy.context.scene.collection.objects.link(empty)
            empty.location = (0, 0, 1.0)
            con = cam_obj.constraints.new(type='TRACK_TO')
            con.target = empty
            con.track_axis = 'TRACK_NEGATIVE_Z'
            con.up_axis = 'UP_Y'
            bpy.context.scene.camera = cam_obj

        def add_light():
            light_data = bpy.data.lights.new(name="key", type='SUN')
            light_obj = bpy.data.objects.new(name="key", object_data=light_data)
            bpy.context.scene.collection.objects.link(light_obj)
            light_obj.rotation_euler = (math.radians(60), 0, math.radians(30))

        def setup_cycles(W, H):
            sc = bpy.context.scene
            sc.render.engine = 'CYCLES'
            sc.cycles.device = 'CPU'
            sc.cycles.samples = 16
            sc.cycles.use_adaptive_sampling = True
            sc.render.resolution_x = int(W)
            sc.render.resolution_y = int(H)
            sc.render.film_transparent = False
            sc.view_layers["ViewLayer"].use_pass_combined = True

        import sys, json, os
        args = sys.argv[sys.argv.index("--")+1:]
        cfg_path, out_png = args[0], args[1]
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
        W = cfg.get("W", 800)
        H = cfg.get("H", 1100)
        target_h_m = float(cfg.get("height_cm", 180.0)) / 100.0

        clear_scene()
        add_mannequin()
        scale_to_height(target_h_m)
        add_camera_front_ortho(ortho_scale=2.3)
        add_light()
        setup_cycles(W, H)

        bpy.context.scene.render.filepath = out_png
        bpy.ops.render.render(write_still=True)
    """)

    with tempfile.TemporaryDirectory() as td:
        cfg = {
            "W": vp.get("width", 800),
            "H": vp.get("height", 1100),
            "height_cm": meas.get("height", 180),
        }
        cfg_path = os.path.join(td, "cfg.json")
        out_png = os.path.join(td, "out.png")
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)

        job_path = os.path.join(td, "job.py")
        with open(job_path, "w") as f:
            f.write(pycode)

        try:
            proc = subprocess.run(
                [BLENDER_BIN, "-b", "-noaudio", "--python", job_path, "--", cfg_path, out_png],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240, text=True
            )
            rc = proc.returncode
            stdout = proc.stdout[-4000:] if proc.stdout else ""
            stderr = proc.stderr[-4000:] if proc.stderr else ""
        except Exception as e:
            return {"ok": False, "png": "", "rc": -2, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}

        if rc != 0 or not os.path.exists(out_png):
            return {"ok": False, "png": "", "rc": rc, "stdout": stdout, "stderr": stderr}

        with open(out_png, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return {"ok": True, "png": "data:image/png;base64," + b64, "rc": rc, "stdout": stdout, "stderr": stderr}

# ---------- Routes ----------

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "tlr-avatar", "version": "blender_2"}

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

@app.get("/blender/health")
def blender_health() -> Dict[str, Any]:
    return {"has_blender": blender_available(), "blender_path": BLENDER_BIN or ""}

@app.get("/blender/smoke")
def blender_smoke() -> JSONResponse:
    res = run_blender_job({"height": 190, "units": "cm"}, "front", {"width": 800, "height": 1100})
    return JSONResponse(res)

@app.get("/blender/smoke_view")
def blender_smoke_view() -> HTMLResponse:
    res = run_blender_job({"height": 190, "units": "cm"}, "front", {"width": 800, "height": 1100})
    if res.get("ok") and res.get("png"):
        html = f"<img style='max-width:100%' src='{res['png']}'/>"
    else:
        html = f"<pre>{json.dumps(res, indent=2)}</pre>"
    return HTMLResponse(html)

@app.post("/avatar/render", response_model=RenderResponse)
def avatar_render(payload: RenderRequest = Body(..., embed=False)) -> JSONResponse:
    want_png = ("png" in payload.return_) or (payload.engine == "blender")
    png_out = ""
    blender_error = ""

    if want_png and blender_available():
        res = run_blender_job(
            meas=payload.measurements.model_dump(),
            view=payload.view,
            vp=payload.viewport.model_dump(),
        )
        if res.get("ok"):
            png_out = res.get("png", "")
        else:
            blender_error = (res.get("stderr") or res.get("stdout") or "unknown_error")[-800:]

    svg_out = ""
    engine_name = "blender"
    if not png_out:
        # fall back to svg so UI never goes blank
        engine_name = "svg"
        svg_out = _fallback_svg(payload.viewport.width, payload.viewport.height)

    meta = {
        "units": payload.measurements.units,
        "pose": payload.pose,
        "engine": engine_name,
        "status": "ok" if (png_out or svg_out) else "error",
    }
    if blender_error:
        meta["blender_error"] = blender_error

    return JSONResponse({"svg": svg_out, "png": png_out, "meta": meta})
