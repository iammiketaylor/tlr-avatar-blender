# main.py  v1.0.2
from typing import List, Optional, Literal, Dict, Any
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
import traceback

# Try to import renderer and capture any error for diagnostics
renderer = None
RENDER_IMPORT_ERROR = ""
RENDERER_VERSION = None

try:
    import render_avatar as renderer  # /app/render_avatar.py
    RENDERER_VERSION = getattr(renderer, "__version__", None)
except Exception as _e:
    RENDER_IMPORT_ERROR = f"{type(_e).__name__}: {str(_e)}\n{traceback.format_exc()}"

app = FastAPI(title="TLR Avatar Render Service", version="1.0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class RenderResponse(BaseModel):
    svg: str = ""
    png: str = ""
    meta: Dict[str, Any] = {}

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "tlr-avatar", "version": "1.0.2"}

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

@app.get("/diagnostics")
def diagnostics() -> Dict[str, Any]:
    return {
        "has_renderer": renderer is not None,
        "renderer_version": RENDERER_VERSION,
        "import_error": RENDER_IMPORT_ERROR,
        "renderer_attrs": sorted([a for a in dir(renderer)]) if renderer else [],
    }

@app.get("/debug/svg")
def debug_svg() -> HTMLResponse:
    sample = {
        "measurements": {
            "units": "cm", "height": 190, "shoulder_width": 48, "chest": 110,
            "waist": 100, "hip": 115, "arm_length": 64, "leg_length": 110,
            "thigh": 65, "calf": 42, "neck": 46
        },
        "pose": "POSE01",
        "view": "front",
        "viewport": {"width": 800, "height": 1100, "ortho": True}
    }
    if renderer and hasattr(renderer, "render_avatar_svg"):
        svg = renderer.render_avatar_svg(sample)
    elif renderer and hasattr(renderer, "render"):
        out = renderer.render(
            measurements=sample["measurements"], pose=sample["pose"],
            view=sample["view"], viewport=sample["viewport"], returns=["svg"]
        )
        svg = out.get("svg", "")
    else:
        svg = "<svg xmlns='http://www.w3.org/2000/svg' width='800' height='1100'><text x='10' y='20'>renderer missing</text></svg>"
    return HTMLResponse(svg)

@app.post("/avatar/render", response_model=RenderResponse)
def avatar_render(payload: RenderRequest = Body(..., embed=False)) -> JSONResponse:
    try:
        svg_out = ""
        png_out = ""
        if renderer is not None:
            if hasattr(renderer, "render"):
                result = renderer.render(
                    measurements=payload.measurements.model_dump(),
                    pose=payload.pose,
                    view=payload.view,
                    viewport=payload.viewport.model_dump(),
                    returns=list(payload.return_),
                )
                if isinstance(result, dict):
                    svg_out = result.get("svg", "") or ""
                    png_out = result.get("png", "") or ""
            elif hasattr(renderer, "render_avatar"):
                result = renderer.render_avatar(payload.model_dump(by_alias=True))
                if isinstance(result, dict):
                    svg_out = result.get("svg", "") or ""
                    png_out = result.get("png", "") or ""
            elif hasattr(renderer, "render_avatar_svg"):
                svg_out = renderer.render_avatar_svg(payload.model_dump(by_alias=True)) or ""

        if not svg_out:
            svg_out = _fallback_svg(payload)

        meta = {
            "units": payload.measurements.units,
            "pose": payload.pose,
            "scale_px_per_cm": 3.0 if payload.measurements.units == "cm" else 3.0 / 2.54,
            "status": "ok" if svg_out else "error",
            "renderer_version": RENDERER_VERSION,
        }

        if "svg" not in payload.return_:
            svg_out = ""
        if "png" not in payload.return_:
            png_out = ""

        return JSONResponse({"svg": svg_out, "png": png_out, "meta": meta})

    except Exception as e:
        return JSONResponse({"svg": "", "png": "", "meta": {"status": "error", "error": str(e)}})

def _fallback_svg(req: RenderRequest) -> str:
    vp = req.viewport
    w = vp.width
    h = vp.height
    cx = w / 2.0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white"/>
  <g stroke="#0B2B4A" fill="none" stroke-width="2">
    <ellipse cx="{cx:.1f}" cy="{h*0.12:.1f}" rx="{w*0.07:.1f}" ry="{h*0.06:.1f}"/>
    <line x1="{cx:.1f}" y1="{h*0.18:.1f}" x2="{cx:.1f}" y2="{h*0.85:.1f}"/>
  </g>
</svg>"""
