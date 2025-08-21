# render_avatar.py  renderer version croquis_0_4
# Clean nine-head croquis. Fixed head placement, smooth closed torso, rounded limbs.

__version__ = "croquis_0_4"

from typing import Dict, Any, List

def render(
    measurements: Dict[str, Any],
    pose: str = "POSE01",
    view: str = "front",
    viewport: Dict[str, Any] = None,
    returns: List[str] = None,
) -> Dict[str, Any]:
    svg = render_avatar_svg({
        "measurements": measurements,
        "pose": pose,
        "view": view,
        "viewport": viewport or {"width": 800, "height": 1100, "ortho": True}
    })
    return {"svg": svg, "png": ""}

def render_avatar(req: Dict[str, Any]) -> Dict[str, Any]:
    return {"svg": render_avatar_svg(req), "png": ""}

def render_avatar_svg(req: Dict[str, Any]) -> str:
    m = req.get("measurements", {}) or {}
    vp = req.get("viewport", {}) or {}
    w = int(vp.get("width", 800))
    h = int(vp.get("height", 1100))

    units = m.get("units", "cm")
    px_per_cm = 3.0 if units == "cm" else 3.0 / 2.54

    # Grid
    Hu = h / 9.0
    y_chin  = 1.00 * Hu
    y_chest = 2.50 * Hu
    y_waist = 3.50 * Hu
    y_hip   = 4.25 * Hu
    y_knee  = 6.50 * Hu
    y_ankle = 8.80 * Hu
    y_shldr = y_chest - 0.25 * Hu
    # Keep neck just under the head, not inside it
    y_neck  = y_chin + 0.05 * Hu

    cx = w / 2.0

    # Measurements with fallbacks
    shoulder_width = _val(m, "shoulder_width", 48.0)
    chest          = _val(m, "chest", 110.0)
    waist          = _val(m, "waist", 100.0)
    hip            = _val(m, "hip", 115.0)
    thigh          = _val(m, "thigh", max(hip * 0.60, 60.0))
    calf           = _val(m, "calf",  max(thigh * 0.65, 38.0))
    upper_arm_w_cm = max(chest / 12.0, 9.0)

    # Convert to half-widths in px
    shoulderW = (shoulder_width / 2.0) * px_per_cm
    chestW    = (chest / 4.0) * px_per_cm
    waistW    = (waist / 4.0) * px_per_cm
    hipW      = (hip / 4.0) * px_per_cm
    upperArmW = upper_arm_w_cm * px_per_cm
    foreArmW  = upperArmW * 0.8
    thighW    = (thigh / 6.0) * px_per_cm
    calfW     = thighW * 0.65

    # Guardrails
    maxW = w * 0.42
    shoulderW = min(shoulderW, maxW)
    chestW    = min(chestW,    maxW)
    waistW    = min(waistW,    maxW)
    hipW      = min(hipW,      maxW)
    upperArmW = min(upperArmW, maxW * 0.6)
    foreArmW  = min(foreArmW,  maxW * 0.6)
    thighW    = min(thighW,    maxW * 0.7)
    calfW     = min(calfW,     maxW * 0.6)

    neckW = min(shoulderW * 0.22, 22.0)

    # Head ellipse where the bottom touches the chin line
    head_ry = 0.45 * Hu
    head_cy = y_chin - head_ry   # bottom = y_chin
    head_rx = w * 0.07

    # Key x positions
    xL = {"hip": cx - hipW, "waist": cx - waistW, "chest": cx - chestW, "shoulder": cx - shoulderW, "neck": cx - neckW}
    xR = {"hip": cx + hipW, "waist": cx + waistW, "chest": cx + chestW, "shoulder": cx + shoulderW, "neck": cx + neckW}

    # Torso as one smooth closed outline using cubic curves
    t = []
    # start at bottom center, go to left hip
    t.append(("M", cx, y_hip + 0.10 * Hu))
    t.append(("L", xL["hip"], y_hip + 0.10 * Hu))
    # left hip -> waist
    t.append(("C",
        xL["hip"], y_hip - 0.18 * Hu,
        xL["waist"] - 0.10 * hipW, y_waist + 0.10 * Hu,
        xL["waist"], y_waist
    ))
    # waist -> chest
    t.append(("C",
        xL["waist"] - 0.10 * waistW, y_waist - 0.12 * Hu,
        xL["chest"] - 0.08 * chestW, y_chest + 0.02 * Hu,
        xL["chest"], y_chest
    ))
    # chest -> shoulder
    t.append(("C",
        xL["chest"] - 0.05 * chestW, y_chest - 0.12 * Hu,
        xL["shoulder"] - 0.10 * shoulderW, y_shldr + 0.02 * Hu,
        xL["shoulder"], y_shldr
    ))
    # shoulder -> neck
    t.append(("C",
        xL["shoulder"] + 0.35 * neckW, y_shldr,
        xL["neck"] + 0.10 * neckW, y_neck + 0.02 * Hu,
        xL["neck"], y_neck
    ))
    # cross neck
    t.append(("L", xR["neck"], y_neck))
    # neck -> shoulder (right)
    t.append(("C",
        xR["neck"] - 0.10 * neckW, y_neck + 0.02 * Hu,
        xR["shoulder"] - 0.35 * neckW, y_shldr,
        xR["shoulder"], y_shldr
    ))
    # shoulder -> chest
    t.append(("C",
        xR["shoulder"] + 0.10 * shoulderW, y_shldr + 0.02 * Hu,
        xR["chest"] + 0.05 * chestW, y_chest - 0.12 * Hu,
        xR["chest"], y_chest
    ))
    # chest -> waist
    t.append(("C",
        xR["chest"] + 0.08 * chestW, y_chest + 0.02 * Hu,
        xR["waist"] + 0.10 * waistW, y_waist - 0.12 * Hu,
        xR["waist"], y_waist
    ))
    # waist -> hip
    t.append(("C",
        xR["waist"] + 0.10 * hipW, y_waist + 0.10 * Hu,
        xR["hip"], y_hip - 0.18 * Hu,
        xR["hip"], y_hip + 0.10 * Hu
    ))
    # back to bottom center
    t.append(("L", cx, y_hip + 0.10 * Hu))
    torso_d = _path(t) + " Z"

    # Arms as tapered capsules with rounded ends
    y_elbow = 0.5 * (y_chest + y_waist)
    y_wrist = y_hip - 0.20 * Hu
    armL = _capsule_tapered(
        x1=xL["shoulder"], y1=y_shldr,
        x2=xL["shoulder"] - upperArmW * 0.35, y2=y_elbow,
        r1=max(upperArmW * 0.35, 6.0), r2=max(foreArmW * 0.30, 5.0),
        end_y=y_wrist
    )
    armR = _capsule_tapered(
        x1=xR["shoulder"], y1=y_shldr,
        x2=xR["shoulder"] + upperArmW * 0.35, y2=y_elbow,
        r1=max(upperArmW * 0.35, 6.0), r2=max(foreArmW * 0.30, 5.0),
        end_y=y_wrist
    )

    # Legs as tapered capsules
    hip_gap = max(hipW * 0.20, 16.0)
    left_hip_x  = cx - hip_gap
    right_hip_x = cx + hip_gap
    legL = _capsule_tapered(
        x1=left_hip_x, y1=y_hip + 0.05 * Hu,
        x2=left_hip_x - thighW * 0.25, y2=y_knee,
        r1=max(thighW * 0.55, 7.0), r2=max(calfW * 0.50, 6.0),
        end_y=y_ankle
    )
    legR = _capsule_tapered(
        x1=right_hip_x, y1=y_hip + 0.05 * Hu,
        x2=right_hip_x + thighW * 0.25, y2=y_knee,
        r1=max(thighW * 0.55, 7.0), r2=max(calfW * 0.50, 6.0),
        end_y=y_ankle
    )

    # Internal grid
    grid = _grid_lines(w, h, Hu)

    # One stroke style for clean joins
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white"/>
  <g opacity="0.10" stroke="#0B2B4A" stroke-width="1">{grid}</g>

  <g stroke="#0B2B4A" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
    <ellipse cx="{cx:.2f}" cy="{head_cy:.2f}" rx="{head_rx:.2f}" ry="{head_ry:.2f}"/>
    <path d="{torso_d}"/>
    <path d="{armL}"/>
    <path d="{armR}"/>
    <path d="{legL}"/>
    <path d="{legR}"/>
  </g>
</svg>'''
    return svg

# helpers

def _val(d: Dict[str, Any], k: str, default: float) -> float:
    try:
        v = float(d.get(k, default))
        return v if v > 0 else default
    except Exception:
        return default

def _path(ops: List[Any]) -> str:
    parts = []
    for op in ops:
        cmd = op[0]
        nums = op[1:]
        if nums:
            parts.append(cmd + " " + " ".join(f"{n:.2f}" for n in nums))
        else:
            parts.append(cmd)
    return " ".join(parts)

def _capsule_tapered(
    x1: float, y1: float, x2: float, y2: float,
    r1: float, r2: float, end_y: float = None
) -> str:
    y_far = end_y if end_y is not None else y2
    cx = (x1 + x2) / 2.0
    cy = (y1 + y_far) / 2.0
    # Rounded tip at far end
    return _path([
        ("M", x1 - r1 * 0.45, y1),
        ("C", cx - r1, cy, cx - r2, cy, x2 - r2 * 0.45, y_far),
        ("C", x2 - r2 * 0.05, y_far + 0.01, x2 + r2 * 0.05, y_far + 0.01, x2 + r2 * 0.45, y_far),
        ("C", cx + r2, cy, cx + r1, cy, x1 + r1 * 0.45, y1),
        ("Z",)
    ])

def _grid_lines(w: int, h: int, Hu: float) -> str:
    ys = [1.0*Hu, 2.5*Hu, 3.5*Hu, 4.25*Hu, 6.5*Hu, 8.8*Hu]
    cx = w / 2.0
    parts = [f'<line x1="{cx:.2f}" y1="0" x2="{cx:.2f}" y2="{h:.2f}"/>' ]
    for y in ys:
        parts.append(f'<line x1="0" y1="{y:.2f}" x2="{w:.2f}" y2="{y:.2f}"/>')
    return "\n    ".join(parts)
