# Blender headless script
# It creates a human with MB-Lab, applies basic measurements, renders PNG, tries to export SVG outline

import bpy, sys, json, os, argparse, base64

def read_json(p):
    with open(p, "r") as f: return json.load(f)

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
    cam.rotation_euler = (1.5708, 0.0, 0.0)
    s.camera = cam

def create_human():
    bpy.ops.mbast.init_character()
    return bpy.context.object

def apply_measurements(human, m):
    P = human.mbast_parameters
    if "height" in m: P.body_height = m["height"] / 100.0
    if "chest"  in m: P.chest = m["chest"] / 100.0
    if "waist"  in m: P.waist = m["waist"] / 100.0
    if "hip"    in m: P.hip   = m["hip"]   / 100.0
    bpy.ops.mbast.update_character()

def set_pose(human, pose_id):
    # neutral for first pass
    return

def render_png(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

def freestyle_svg(svg_path):
    s = bpy.context.scene
    s.render.use_freestyle = True
    s.view_layers["View Layer"].freestyle_settings.linesets.new("LineSet")
    try:
        bpy.ops.render.freestyle_svg_export(filepath=svg_path, use_fill=False)
        with open(svg_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100"/>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out", dest="outdir", required=True)
    args = ap.parse_args(sys.argv[sys.argv.index("--")+1:])

    req = read_json(args.infile)
    m   = req.get("measurements", {})
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

    result = {"svg": svg, "png": png_data_url(png_path), "meta": {"units":"cm","pose":pose}}
    with open(os.path.join(args.outdir, "result.json"), "w") as f:
        json.dump(result, f)

if __name__ == "__main__":
    main()
