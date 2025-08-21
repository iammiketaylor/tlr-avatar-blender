from fastapi import FastAPI
from fastapi.responses import JSONResponse
import subprocess, tempfile, json, os

BLENDER = "/opt/blender/blender"
SCRIPT  = "/app/render_avatar.py"

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.post("/avatar/render")
def render(payload: dict):
    with tempfile.TemporaryDirectory() as tmp:
        req_path = os.path.join(tmp, "req.json")
        out_dir  = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        with open(req_path, "w") as f:
            json.dump(payload, f)
        cmd = [BLENDER, "-b", "-P", SCRIPT, "--", "--in", req_path, "--out", out_dir]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        result_path = os.path.join(out_dir, "result.json")
        if not os.path.exists(result_path):
            svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="1100"/>'
            return JSONResponse({"svg": svg, "png": "", "meta": {"error": "render failed"}})
        with open(result_path, "r") as f:
            data = json.load(f)
        return JSONResponse(data)
