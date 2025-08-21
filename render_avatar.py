# Blender headless script
# Creates an MB-Lab human, applies basic measurements, renders PNG, tries to export outline SVG

import bpy, sys, json, os, argparse, base64

def read_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def png_data_url(p):
    with open(p, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

def setup_scene(w=800, h=1100):
    s = bpy.context.scene
    s.render.engine = "BLENDER_EEVEE"
    s.render.image_settings.file_format = "PNG"
    s.render.resolution_x = w
    s.render.resolution_y = h

    cam = bpy.data.objects.get("Camera")
    if not cam:
        bpy.ops.object.camera_add()
        cam = bpy.context.object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.4
    cam.location = (0, -10, 1.6)
    cam.rotation_euler = (1.5708, 0.0, 0.0)  # look +Y
    s.camera = cam

    # simple flat light
    if "Key" not in bpy.data.objects:
        bpy.ops.object.light_add(type='AREA', location=(0, -5, 2))

def create_human():
    # MB-Lab operator
    bpy.ops.mbast.init_character()
    return bpy.context.object

def apply_measurements(human, m):
    # minimal working mapping. we refine once service is live
    # MB-Lab parameter names vary by version. This uses common ones.
    P = getattr(human, "mbast_parameters", None)
    if not P:
        return
    # Inputs are in cm. MB-Lab uses meters for many props
    def cm(val): return (val or 0) / 100.0

    if "height" in m and m["height"]:
        P.body_height = cm(m["height"])
    if "chest" in m and m["chest"]:
        P.chest = cm(m["chest"])
    if "waist" in m and m["waist"]:
        P.waist = cm(m["waist"])
    if "hip" in m and m["hip"]:
        P.hip = cm(m["hip"])
    # Add more fields as we validate exact prop names in this MB-Lab build

    try:
        bpy.ops.mbast.update_character()
    except Exception:
        pass

def set_pose(human, pose_id):
    # Neutral for first pass. Later map POSE01.. to actions or BVH.
    return

def render_png(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

def freestyle_svg(svg_path):
    # Try Freestyle SVG export if available
    s = bpy.context.scene
    s.render.use_freestyle = True
    try:
        if "View Layer" in bpy.context.view_layer.name:
            pass
        # Create a lineset if none exists
        fls = bpy.context.view_layer.freestyle_settings
        if not fls.linesets:
            fls.linesets.new("LineSet")

        bpy.ops.render.freestyle_svg_export(filepath=svg_path, use_fill=False)
        with open(svg_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        # fallback empty svg if Freestyle not available
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100"></svg>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outdir", required=True)
    # Parse args after the -- marker Blender passes
    args = ap.parse_args(sys.argv[sys.argv.index("--")+1:])

    req = read_json(args.infile)
    m   = req.get("measurements", {}) or {}
    pose= req.get("pose", "POSE01")

    setup_scene()
    human = create_human()
    apply_measurements(human, m)
    set_pose(human, pose)

    os.makedirs(args.outdir, exist_ok=True)
    png_path = os.path.join(args.outdir, "avatar.png")
    svg_path = os.path.join(args.outdir, "avatar.svg")

    render_png(png_path)
    svg = freestyle_svg(svg_path)

    result = {
        "svg": svg,
        "png": png_data_url(png_path),
        "meta": {"units":"cm","pose":pose}
    }
    with open(os.path.join(args.outdir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f)

if __name__ == "__main__":
    main()
