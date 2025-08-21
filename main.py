# main.py
from typing import List, Optional, Literal, Dict, Any
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Try to import your renderer without assuming a single function name
# We will try common call shapes used in our earlier steps
try:
    import render_avatar as renderer  # your /app/render_avatar.py
except Exception as _e:
    renderer = None

app = FastAPI(title="TLR Avatar Render Service", version="1.0.0")

# CORS so the Studio can call this directly from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock down to your domains when ready
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Request and response models ----------

class Viewport(BaseModel):
    width: int = 800
    height: int = 1100
    ortho: bool = True

class Measurements(BaseModel):
    units: Literal["cm", "in"] = "cm"
    height: float = Field(..., description="Total body height")
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

# ---------- Health ----------

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

# ---------- Core render route ----------

@app.post("/avatar/render", response_model=RenderResponse)
def avatar_render(payload: RenderRequest = Body(..., embed=False)) -> JSONResponse:
    """
    Returns svg and or png with a small meta object.
    Matches the avatar_engine_contract in your pickup file.
    """
    try:
        svg_out = ""
        png_out = ""

        # Prefer renderer if available
        if renderer is not None:
            # Accept multiple possible function signatures for safety
            # 1) render(measurements=dict, pose=str, view=str, viewport=dict, returns=list[str])
            if hasattr(renderer, "render"):
                result = renderer.render(
                    measurements=payload.measurements.model_dump(),
                    pose=payload.pose,
                    view=payload.view,
                    viewport=payload.viewport.model_dump(),
                    returns=list(payload.return_),
                )
                svg_out = result.get("svg", "") if isinstance(result, dict) else ""
                png_out = result.get("png", "") if isinstance(result, dict) else ""
            # 2) render_avatar or render_avatar_svg style
            elif hasattr(renderer, "render_avatar"):
                result = renderer.render_avatar(payload.model_dump(by_alias=True))
                svg_out = result.get("svg", "") if isinstance(result, dict) else ""
                png_out = result.get("png", "") if isinstance(result, dict) else ""
            elif hasattr(renderer, "render_avatar_svg"):
                svg_out = renderer.render_avatar_svg(payload.model_dump(by_alias=True))
                # png is optional here
        else:
            # Safe fallback so the Studio never goes blank
            svg_out = _fallback_svg(payload)

        meta = {
            "units": payload.measurements.units,
            "pose": payload.pose,
            "scale_px_per_cm": 3.0 if payload.measurements.units == "cm" else 3.0 / 2.54,
            "status": "ok",
        }

        # Respect the requested return set
        if "svg" not in payload.return_:
            svg_out = ""
        if "png" not in payload.return_:
            png_out = ""

        return JSONResponse({"svg": svg_out, "png": png_out, "meta": meta})

    except Exception as e:
        # Never crash. Return structured error the Studio can handle
        return JSONResponse(
            {
                "svg": "",
                "png": "",
                "meta": {
                    "error": str(e),
                    "status": "error",
                },
            }
        )

# ---------- Root ----------

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "tlr-avatar", "version": "1.0.0"}


# ---------- Simple fallback renderer so Outline mode always has something ----------

def _fallback_svg(req: RenderRequest) -> str:
    vp = req.viewport
    w = vp.width
    h = vp.height
    # A minimal croquis oval and a guide line so the UI shows Outline view on day one
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white"/>
  <g stroke="black" fill="none" stroke-width="2">
    <ellipse cx="{w/2:.1f}" cy="{h*0.12:.1f}" rx="{w*0.07:.1f}" ry="{h*0.06:.1f}"/>
    <line x1="{w/2:.1f}" y1="{h*0.12 + h*0.06:.1f}" x2="{w/2:.1f}" y2="{h*0.85:.1f}"/>
  </g>
</svg>"""
