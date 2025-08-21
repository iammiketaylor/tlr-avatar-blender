from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import subprocess, tempfile, json, os

BLENDER = "/opt/blender/blender"
SCRIPT  = "/app/render_avatar.py"

app = FastAPI()

# CORS so Base44 or Studio in the browser can call this directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later to your Base44 domain if you want
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"ok": True}

@app.post("/avatar/render")
def render(payload: dict):
    # payload expected keys:
    #   measurements: { units:"cm", height, chest, waist, hip, shoulder_width?, arm_length?, leg_length?, thigh?, calf?, neck? }
    #   pose: "POSE01"
    #   view: "front"
    #   return: ["svg","png"]
    #   viewport: { width: 800, height: 1100, ortho: true }
    with tempfile.TemporaryDirectory() as tmp:
        req_path = os.path.join(tmp, "req.json")
        out_dir  = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)

        with open(req_path, "w") as f:
            json.dump(payload or {}, f)

        cmd = [BLENDER, "-b", "-P", SCRIPT, "--", "--in", req_path, "--out", out_dir]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        result_path = os.path.join(out_dir, "result.json")
        if not os.path.exists(result_path):
            # fallback so Studio never breaks
            svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100"/>'
            return JSONResponse({"svg": svg, "png": "", "meta": {"error": "render failed", "stderr": proc.stderr.decode("utf-8", "ignore")}})

        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return JSONResponse(data)

            return JSONResponse({"svg": svg, "png": "", "meta": {"error": "render failed"}})
        with open(result_path, "r") as f:
            data = json.load(f)
        return JSONResponse(data)
