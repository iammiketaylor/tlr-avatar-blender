# main.py  blender_cycles_safe
from typing import Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
import base64, json, os, subprocess, tempfile, textwrap, shutil

app = FastAPI(title="TLR Avatar Render Service", version="blender_cycles_safe")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True, "service": "tlr-avatar", "version": "blender_cycles_safe"}

@app.get("/health")
def health():
    return {"ok": True}

BLENDER_BIN = shutil.which("blender")

@app.get("/blender/health")
def blender_health():
    return {"has_blender": BLENDER_BIN is not None, "blender_path": BLENDER_BIN or ""}

def run_blender_smoke(W: int = 800, H: int = 1100, height_cm: float = 190) -> Dict[str, Any]:
    if not BLENDER_BIN:
        return {"ok": False, "png": "", "rc": -1, "stdout": "", "stderr": "blender_not_found"}

    pycode = textwrap.dedent("""
        import bpy, sys, json, math
        from mathutils import Vector

        def clear():
            bpy.ops.wm.read_homefile(use_empty=True)
            for o in list(bpy.data.objects):
                try: bpy.data.objects.remove(o, do_unlink=True)
                except: pass

        def mat():
            m = bpy.data.materials.new("BodyMat")
            m.use_nodes = True
            bsdf = m.node_tree.nodes.get("Principled BSDF")
            bsdf.inputs["Base Color"].default_value = (0.7,0.72,0.75,1.0)
            bsdf.inputs["Roughness"].default_value = 0.6
            return m

        def add_parts(M):
            def add(op, **kw):
                getattr(bpy.ops.mesh, op)(**kw)
                o = bpy.context.active_object
                if o and o.data and hasattr(o.data,"materials"):
                    if not o.data.materials: o.data.materials.append(M)
                    else: o.data.materials[0] = M
            add("primitive_uv_sphere_add", radius=0.12, location=(0,0,1.80))
            add("primitive_cylinder_add", radius=0.20, depth=0.60, location=(0,0,1.40))
            add("primitive_cylinder_add", radius=0.22, depth=0.40, location=(0,0,1.00))
            add("primitive_cylinder_add", radius=0.10, depth=0.70, location=(-0.25,0,1.25))
            add("primitive_cylinder_add", radius=0.10, depth=0.70, location=( 0.25,0,1.25))
            add("primitive_cylinder_add", radius=0.12, depth=1.00, location=(-0.12,0,0.40))
            add("primitive_cylinder_add", radius=0.12, depth=1.00, location=( 0.12,0,0.40))

        def world_and_light():
            if bpy.context.scene.world is None:
                bpy.context.scene.world = bpy.data.worlds.new("World")
            w = bpy.context.scene.world
            w.use_nodes = True
            bg = w.node_tree.nodes.get("Background")
            if bg:
                bg.inputs[0].default_value = (1,1,1,1)
                bg.inputs[1].default_value = 5.0
            sun = bpy.data.lights.new("sun","SUN")
            sun.energy = 5.0
            so = bpy.data.objects.new("sun",sun)
            bpy.context.scene.collection.objects.link(so)
            so.location = (3.0,2.0,4.0)
            so.rotation_euler = (math.radians(50),0,math.radians(-20))

        def camera_ortho(scale=2.8):
            cam = bpy.data.cameras.new("cam"); cam.type='ORTHO'; cam.ortho_scale = scale
            co = bpy.data.objects.new("cam", cam)
            bpy.context.scene.collection.objects.link(co)
            co.location = (0.0,-5.0,1.2)
            tgt = bpy.data.objects.new("target", None)
            bpy.context.scene.collection.objects.link(tgt)
            tgt.location = (0.0,0.0,1.0)
            con = co.constraints.new(type='TRACK_TO'); con.target = tgt
            con.track_axis='TRACK_NEGATIVE_Z'; con.up_axis='UP_Y'
            bpy.context.scene.camera = co

        def setup_cycles(W,H):
            sc = bpy.context.scene
            sc.render.engine = 'CYCLES'
            sc.cycles.device = 'CPU'
            sc.cycles.samples = 8
            sc.cycles.use_adaptive_sampling = True
            sc.view_settings.view_transform = 'Standard'
            sc.render.resolution_x = int(W)
            sc.render.resolution_y = int(H)
            sc.render.film_transparent = False
            sc.render.image_settings.file_format = 'PNG'

        args = sys.argv[sys.argv.index("--")+1:]
        cfg_path, out_png = args[0], args[1]
        with open(cfg_path,"r") as f: cfg = json.load(f)
        W = cfg.get("W",800); H = cfg.get("H",1100); height_cm = cfg.get("height_cm",190)

        clear()
        add_parts(mat())
        world_and_light()
        camera_ortho()
        setup_cycles(W,H)

        # scale to height after everything is placed
        from mathutils import Vector
        deps = bpy.context.evaluated_depsgraph_get()
        zmin,zmax = 1e9,-1e9
        for o in bpy.data.objects:
            if o.type!="MESH": continue
            eo = o.evaluated_get(deps); M = eo.matrix_world
            for x,y,z in eo.bound_box:
                v = M @ Vector((x,y,z))
                zmin = min(zmin,v.z); zmax = max(zmax,v.z)
        cur_h = max(0.01, zmax - zmin)
        s = (height_cm/100.0)/cur_h
        for o in bpy.data.objects:
            if o.type in {"MESH","ARMATURE","EMPTY"}:
                o.scale *= s

        bpy.ops.render.render(write_still=True)
        bpy.data.images['Render Result'].save_render(out_png)
    """)

    with tempfile.TemporaryDirectory() as td:
        cfg = {"W": W, "H": H, "height_cm": height_cm}
        cfg_path = os.path.join(td, "cfg.json")
        out_png = os.path.join(td, "out.png")
        open(cfg_path, "w").write(json.dumps(cfg))
        job = os.path.join(td, "job.py"); open(job, "w").write(pycode)

        try:
            proc = subprocess.run([BLENDER_BIN, "-b", "-noaudio", "--python", job, "--", cfg_path, out_png],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300, text=True)
            rc = proc.returncode
            stdout = proc.stdout[-4000:] if proc.stdout else ""
            stderr = proc.stderr[-4000:] if proc.stderr else ""
        except Exception as e:
            return {"ok": False, "png": "", "rc": -2, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}

        if rc != 0 or not os.path.exists(out_png):
            return {"ok": False, "png": "", "rc": rc, "stdout": stdout, "stderr": stderr}

        b64 = base64.b64encode(open(out_png, "rb").read()).decode("ascii")
        return {"ok": True, "png": "data:image/png;base64,"+b64, "rc": rc, "stdout": stdout, "stderr": stderr}

@app.get("/blender/smoke")
def blender_smoke():
    res = run_blender_smoke(800, 1100, 190)
    return JSONResponse(res)

@app.get("/blender/smoke_view")
def blender_smoke_view():
    res = run_blender_smoke(800, 1100, 190)
    if res.get("ok") and res.get("png"):
        return HTMLResponse(f"<img style='max-width:100%;background:#fff' src='{res['png']}'/>")
    return HTMLResponse(f"<pre>{json.dumps(res, indent=2)}</pre>")
