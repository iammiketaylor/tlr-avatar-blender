# main.py
from typing import List, Optional, Literal, Dict, Any
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import sys
import traceback

# Try to import renderer and record any error so we can see it from /diagnostics
renderer = None
RENDER_IMPORT_ERROR = ""

try:
    import render_avatar as renderer  # /app/render_avatar.py
except Exception as _e:
    RENDER_IMPORT_ERROR = f"{type(_e).__name__}: {str(_e)}\n{traceback.format_exc()}"

app = FastAPI(title="TLR Avatar Render Service", version="1.0.1")

# CORS for Studio
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

class RenderResponse(BaseModel):
    svg: str = ""
    png: str = ""
    meta: Dict[str, Any] = {}

# ---------- Routes ----------

@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "tlr-avatar", "version": "1.0.1"}

@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

@app.get("/diagnostics")
def diagnostics() -> Dict[str, Any]:
    """See if the renderer was imported and what symbols it exposes."""
    info = {
        "has_renderer": renderer is not None,
        "import_error": RENDER_IMPORT_ERROR,
        "renderer_attrs": [],
    }
    if renderer is not None:
        info["renderer_attrs"] = sorted([a for a in dir(renderer) if not a.startswith("_")])
    return info

@app.post("/test/renderer")
def test_renderer(payload: dict = Body(default=None)) -> JSONResponse:
    """Call the renderer directly with a tiny payload to see exceptions plainly."""
    if renderer is None:
        return JSONResponse({
            "ok": False,
            "error": "renderer_not_loaded",
            "import_error": RENDER_IMPORT_ERROR,
        })
    try:
        sample = {
            "measurements": {
                "units": "cm",
                "height": 190,
                "shoulder_width": 48,
                "chest": 110,
                "waist": 100,
                "hip": 115,
                "arm_length": 64,
                "leg_length": 110,
                "thigh": 65,
                "calf": 42,
                "neck": 46
            },
            "pose": "POSE01",
            "view": "front",
            "viewport": {"width": 800, "height": 1100, "ortho": True}
        }
        if payload and isinstance(payload, dict):
            sample.update(payload)
        # Prefer render(), fall back to render_avatar(), then render_avatar_svg()
        if hasattr(renderer, "render"):
            out = renderer.render(
                measurements=sample["measurements"],
                pose=sample["pose"],
                view=sample["view"],
                viewport=sample["viewport"],
                returns=["svg"]
            )
        elif hasattr(renderer, "render_avatar"):
            out = renderer.render_avatar(sample)
        elif hasattr(renderer, "render_avatar_svg"):
            svg = renderer.render_avatar_svg(sample)
            out = {"svg": svg, "png": ""}
        else:
            return JSONResponse({"ok": False, "error": "no_render_functions_found"})
        return JSONResponse({"ok": True, "out": out})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e), "trace": traceback.format_exc()})

@app.post("/avatar/render", response_model=RenderResponse)
def avatar_render(payload: RenderRequest = Body(..., embed=False)) -> JSONResponse:
    try:
        svg_out = ""
        png_out = ""

        if renderer is not None:
            try:
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
                elif hasattr(renderer, "render_avatar"):
                    result = renderer.render_avatar(payload.model_dump(by_alias=True))
                    svg_out = result.get("svg", "") if isinstance(result, dict) else ""
                    png_out = result.get("png", "") if isinstance(result, dict) else ""
                elif hasattr(renderer, "render_avatar_svg"):
                    svg_out = renderer.render_avatar_svg(payload.model_dump(by_alias=True))
                else:
                    # No callable renderer found, fall through to fallback
                    pass
            except Exception as re:
                # Renderer threw. Return structured error and no blank UI.
                return JSONResponse({
                    "svg": _fallback_svg(payload),
                    "png": "",
                    "meta": {
                        "units": payload.measurements.units,
                        "pose": payload.pose,
                        "scale_px_per_cm": 3.0 if payload.measurements.units == "cm" else 3.0 / 2.54,
                        "status": "error",
                        "error": f"renderer_exception: {type(re).__name__}: {str(re)}",
                    },
                })

        if not svg_out:
            # Renderer missing or returned empty: provide fallback so Studio shows something
            svg_out = _fallback_svg(payload)

        meta = {
            "units": payload.measurements.units,
            "pose": payload.pose,
            "scale_px_per_cm": 3.0 if payload.measurements.units == "cm" else 3.0 / 2.54,
            "status": "ok" if svg_out else "error",
        }
        if renderer is None:
            meta["warning"] = "renderer_not_loaded"
            if RENDER_IMPORT_ERROR:
                meta["import_error"] = RENDER_IMPORT_ERROR

        # Respect requested returns
        if "svg" not in payload.return_:
            svg_out = ""
        if "png" not in payload.return_:
            png_out = ""

        return JSONResponse({"svg": svg_out, "png": png_out, "meta": meta})

    except Exception as e:
        return JSONResponse({
            "svg": "",
            "png": "",
            "meta": {"status": "error", "error": str(e)}
        })

# ---------- Fallback art ----------

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
