# main.py  3D switch-on: adds Blender PNG path while keeping SVG fallback

from typing import List, Optional, Literal, Dict, Any
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import base64, json, os, subprocess, tempfile, textwrap, shutil

app = FastAPI(title="TLR Avatar Render Service", version="blender_1")

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
    engine: Optional[Literal["svg","blender"]] = None  # if "blender", force PNG path

class RenderResponse(BaseModel):
    svg: str = ""
    png: str = ""
    meta: Dict[str, Any] = {}

# ---------- Small SVG fallback so UI never goes blank ----------

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

BLENDER_BIN = shutil.which("blender")  # must not be None if Blender is installed

def blender_available() -> bool:
    return BLENDER_BIN is not None

def run_blender_job(meas: Dict[str, Any], view: str, vp: Dict[str, Any]) -> Optional[str]:
    """
    Runs Blender in background to render a front PNG.
    Tries to enable MB-Lab if present and create a default human.
    If MB-Lab is not available, renders a simple mannequin made from primitives.
    Returns base64 data url or None on failure.
    """
    if not blender_available():
        return None

    pycode = textwrap.dedent("""
        import bpy, sys, json, math

        args = sys.argv[sys.argv.index("--")+1:]
        in_json = args[0]
        out_png = args[1]

        with open(in_json, "r") as f:
            cfg = json.load(f)

        W = int(cfg.get("W", 800))
        H = int(cfg.get("H", 1100))
        units = cfg.get("units","cm")
        height_cm = float(cfg.get("height", 180.0))

        # clean scene
        bpy.ops.wm.read_homefile(use_empty=True)
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        # try to enable MB-Lab
        try:
            bpy.ops.preferences.addon_enable(module="MB-Lab")
            has_mblab = True
        except Exception:
            has_mblab = False

        # create character
        created = False
        if has_mblab:
            # try a few known operators across MB-Lab versions
            tried = False
            for op in [
                "mb_lab.character_creation",
                "mb_lab.init_character",
                "mb_lab.create_character",
            ]:
                try:
                    getattr(bpy.ops, op.replace(".", "_"))()
                    created = True
                    break
                except Exception:
                    pass

        if not created:
            # simple mannequin fallback: sphere head, capsule body and limbs
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.12, location=(0, 0, 1.80))
            bpy.ops.mesh.primitive_cylinder_add(radius=0.20, depth=0.60, location=(0, 0, 1.40))  # upper torso
            bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.40, location=(0, 0, 1.00))  # lower torso
            bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.70, location=(-0.25, 0, 1.25))  # arm L
            bpy.ops.mesh.primitive_cylinder_add(radius=0.10, depth=0.70, location=( 0.25, 0, 1.25))  # arm R
            bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.00, location=(-0.12, 0, 0.40))  # leg L
            bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.00, location=( 0.12, 0, 0.40))  # leg R
        else:
            # scale character to requested height if possible
            try:
                # estimate current figure height using object bounds
                char = [o for o in bpy.data.objects if o.type == "MESH"]
                if char:
                    bbox = char[0].bound_box
                    zmin = min([v[2] for v in bbox])
                    zmax = max([v[2] for v in bbox])
                    cur_h = max(0.01, zmax - zmin)
                else:
                    cur_h = 1.7
                target_h = height_cm / 100.0
                scale = target_h / cur_h
                for o in bpy.data.objects:
                    if o.type in {"MESH", "ARMATURE"}:
                        o.scale *= scale
            except Exception:
                pass

        # camera orthographic front
        cam = bpy.data.cameras.new("cam")
        cam.type = 'ORTHO'
        cam.ortho_scale = 1.8  # wide enough to see full body
        cam_obj = bpy.data.objects.new("cam", cam)
        bpy.context.scene.collection.objects.link(cam_obj)
        cam_obj.location = (0, -5.0, 1.0)
        cam_obj.rotation_euler = (math.radians(90), 0, 0)
        bpy.context.scene.camera = cam_obj

        # light
        light_data = bpy.data.lights.new(name="key", type='SUN')
        light_obj = bpy.data.objects.new(name="key", object_data=light_data)
        bpy.context.scene.collection.objects.link(light_obj)
        light_obj.rotation_euler = (math.radians(60), 0, math.radians(30))

        # render settings
        scene = bpy.context.scene
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x = W
        scene.render.resolution_y = H
        scene.render.film_transparent = False
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = out_png

        bpy.ops.render.render(write_still=True)
    """)

    with tempfile.TemporaryDirectory() as td:
        in_json = os.path.join(td, "cfg.json")
        out_png = os.path.join(td, "out.png")
        with open(in_json, "w") as f:
            json.dump({
                "W": vp.get("width", 800),
                "H": vp.get("height", 1100),
                "units": meas.get("units","cm"),
                "height": meas.get("height", 180)
            }, f)
        job = os.path.join(td, "job.py")
        with open(job, "w") as f:
            f.write(pycode)
        try:
            proc = subprocess.run(
                [BLENDER_BIN, "-b", "-noaudio", "--python", job, "--", in_json, out_png],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180
            )
        except Exception:
            return None
        if not os.path.exists(out_png):
            return None
        with open(out_png, "rb") as f:
            b = base64.b64encode(f.read()).decode("ascii")
        return "data:image/png;base64," + b

# ---------- Routes ----------

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "tlr-avatar", "version": "blender_1"}

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

@app.get("/blender/health")
def blender_health() -> Dict[str, Any]:
    return {"has_blender": blender_available(), "blender_path": BLENDER_BIN or ""}

@app.post("/avatar/render", response_model=RenderResponse)
def avatar_render(payload: RenderRequest = Body(..., embed=False)) -> JSONResponse:
    want_png = ("png" in payload.return_) or (payload.engine == "blender")
    svg_out = ""
    png_out = ""

    if want_png and blender_available():
        png_out = run_blender_job(
            meas=payload.measurements.model_dump(),
            view=payload.view,
            vp=payload.viewport.model_dump()
        ) or ""

    # keep svg empty if we are using Blender, otherwise return the simple svg fallback
    if not png_out:
        svg_out = _fallback_svg(payload.viewport.width, payload.viewport.height)

    meta = {
        "units": payload.measurements.units,
        "pose": payload.pose,
        "engine": "blender" if png_out else "svg",
        "status": "ok" if (png_out or svg_out) else "error",
    }
    return JSONResponse({"svg": svg_out, "png": png_out, "meta": meta})
