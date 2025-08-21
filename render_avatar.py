# render_avatar.py
# TLR lightweight SVG renderer for the Avatar service
# Returns an SVG croquis built on a nine-head grid using measurement-driven widths.

from typing import Dict, Any, List

def render(
    measurements: Dict[str, Any],
    pose: str = "POSE01",
    view: str = "front",
    viewport: Dict[str, Any] = None,
    returns: List[str] = None,
) -> Dict[str, Any]:
    """
    Primary entry point expected by main.py.
    Returns dict with keys: svg, png
    """
    svg = render_avatar_svg({
        "measurements": measurements,
        "pose": pose,
        "view": view,
        "viewport": viewport or {"width": 800, "height": 1100, "ortho": True}
    })
    out = {"svg": svg, "png": ""}
    return out

def render_avatar(req: Dict[str, Any]) -> Dict[str, Any]:
    """Secondary entry for safety. Same output shape as render()."""
    svg = render_avatar_svg(req)
    return {"svg": svg, "png": ""}

def render_avatar_svg(req: Dict[str, Any]) -> str:
    """
    Build an SVG using the nine head unit system:
    Hu = total height in px / 9
    Landmarks:
      chin 1Hu, chest 2.5Hu, waist 3.5Hu, hip 4.25Hu, knee 6.5Hu, ankle 8.8Hu
    Width rules adapt from measurements with a px-per-cm scale.
    """
    m = req.get("measurements", {}) or {}
    vp = req.get("viewport", {}) or {}
    w = int(vp.get("width", 800))
    h = int(vp.get("height", 1100))

    # Scale settings
    units = m.get("units", "cm")
    # Use the same px-per-cm the service advertises in meta so Studio math stays consistent
    px_per_cm = 3.0 if units == "cm" else 3.0 / 2.54

    # Head unit grid
    Hu = h / 9.0
    y_chin = 1.0 * Hu
    y_chest = 2.5 * Hu
    y_waist = 3.5 * Hu
    y_hip = 4.25 * Hu
    y_knee = 6.5 * Hu
    y_ankle = 8.8 * Hu

    cx = w / 2.0

    # Measurements with reasonable fallbacks
    shoulder_width = _val(m, "shoulder_width", 48.0)  # cm
    chest = _val(m, "chest", 110.0)                   # cm
    waist = _val(m, "waist", 100.0)                   # cm
    hip = _val(m, "hip", 115.0)                       # cm
    thigh = _val(m, "thigh", max(hip * 0.60, 60.0))   # cm
    calf = _val(m, "calf", max(thigh * 0.65, 38.0))   # cm
    upper_arm_w_cm = max(chest / 12.0, 9.0)

    # Convert girths to half-widths in px using simple tailoring proportions
    shoulderW = (shoulder_width / 2.0) * px_per_cm
    chestW = (chest / 4.0) * px_per_cm
    waistW = (waist / 4.0) * px_per_cm
    hipW = (hip / 4.0) * px_per_cm
    upperArmW = upper_arm_w_cm * px_per_cm
    foreArmW = upperArmW * 0.8
    thighW = (thigh / 6.0) * px_per_cm
    calfW = thighW * 0.65

    # Guardrails so the drawing stays on screen
    maxW = w * 0.42
    shoulderW = min(shoulderW, maxW)
    chestW = min(chestW, maxW)
    waistW = min(waistW, maxW)
    hipW = min(hipW, maxW)
    upperArmW = min(upperArmW, maxW * 0.6)
    foreArmW = min(foreArmW, maxW * 0.6)
    thighW = min(thighW, maxW * 0.7)
    calfW = min(calfW, maxW * 0.6)

    # Head
    head_rx = w * 0.07
    head_ry = Hu * 0.60
    head_cy = Hu * 0.95  # a touch above exact 1Hu so the chin lands near 1Hu

    # Torso bezier half outline then mirrored
    # Control points add a mild S-curve so the silhouette feels like a croquis, not a stick
    # Left half
    torso_path_left = _path([
        ("M", cx, y_chin),
        ("C", cx - shoulderW, y_chest - 0.5*Hu,
              cx - chestW * 1.02, y_chest,
              cx - chestW * 1.00, y_chest + 0.25*Hu),
        ("S", cx - waistW * 0.95, y_waist,
              cx - waistW * 0.98, y_waist + 0.15*Hu),
        ("S", cx - hipW, y_hip,
              cx - hipW, y_hip + 0.10*Hu),
        ("L", cx, y_hip + 0.10*Hu)  # center bottom torso
    ])

    # Arms as tapered capsules with slight bend
    y_shoulder = y_chest - 0.25*Hu
    y_elbow = (y_chest + y_waist) / 2.0
    y_wrist = y_hip - 0.2*Hu
    armL = _capsule_tapered(cx - shoulderW, y_shoulder, cx - shoulderW - upperArmW*0.35, y_elbow,
                            upperArmW*0.5, foreArmW*0.45)
    armR = _capsule_tapered(cx + shoulderW, y_shoulder, cx + shoulderW + upperArmW*0.35, y_elbow,
                            upperArmW*0.5, foreArmW*0.45)

    # Legs as tapered long capsules
    hip_gap = max(hipW * 0.20, 16.0)
    left_hip_x = cx - hip_gap
    right_hip_x = cx + hip_gap

    legL = _capsule_tapered(left_hip_x, y_hip + 0.05*Hu, left_hip_x - thighW*0.25, y_knee,
                            thighW*0.60, calfW*0.55, y2=y_ankle)
    legR = _capsule_tapered(right_hip_x, y_hip + 0.05*Hu, right_hip_x + thighW*0.25, y_knee,
                            thighW*0.60, calfW*0.55, y2=y_ankle)

    # Mirror torso to form closed body
    torso_path_right = mirror_path_h(torso_path_left, cx)
    torso_path = torso_path_left + " " + torso_path_right + " Z"

    # Grid lines for internal guide
    grid = _grid_lines(w, h, Hu)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="100%" height="100%" fill="white"/>
  <g opacity="0.10" stroke="#0B2B4A" stroke-width="1">{grid}</g>

  <!-- Head -->
  <g stroke="#0B2B4A" stroke-width="2" fill="none">
    <ellipse cx="{cx:.2f}" cy="{head_cy:.2f}" rx="{head_rx:.2f}" ry="{head_ry:.2f}"/>
  </g>

  <!-- Torso -->
  <path d="{torso_path}" fill="none" stroke="#0B2B4A" stroke-width="2"/>

  <!-- Arms -->
  <path d="{armL}" fill="none" stroke="#0B2B4A" stroke-width="2"/>
  <path d="{armR}" fill="none" stroke="#0B2B4A" stroke-width="2"/>

  <!-- Legs -->
  <path d="{legL}" fill="none" stroke="#0B2B4A" stroke-width="2"/>
  <path d="{legR}" fill="none" stroke="#0B2B4A" stroke-width="2"/>

</svg>'''
    return svg

# Helpers

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
        parts.append(cmd + " " + " ".join(f"{n:.2f}" for n in nums))
    return " ".join(parts)

def _capsule_tapered(x1: float, y1: float, x2: float, y2: float,
                     r1: float, r2: float, y2_override: float = None, y2=None) -> str:
    """
    Draw a tapered limb as two curves that meet at the far end.
    x1,y1 near the body with radius r1
    toward x2,y2 with radius r2
    If y2 is provided, it overrides y2 from args to allow ankle target.
    """
    if y2 is None and y2_override is not None:
        y2 = y2_override
    if y2 is None:
        y2 = y2_override if y2_override is not None else y2

    # Slight bend control
    cx = (x1 + x2) / 2.0
    cy = (y1 + (y2 if y2 is not None else y2)) / 2.0 if (y2 is not None) else (y1 + y2) / 2.0

    y2_final = y2 if y2 is not None else y2

    return _path([
        ("M", x1 - r1 * 0.5, y1),
        ("C", cx - r1, cy, cx - r2, cy, x2 - r2 * 0.5, y2_final),
        ("L", x2 + r2 * 0.5, y2_final),
        ("C", cx + r2, cy, cx + r1, cy, x1 + r1 * 0.5, y1),
        ("Z",)
    ])

def mirror_path_h(path_d: str, x_axis: float) -> str:
    """
    Mirror a path string horizontally around x = x_axis.
    This is a simple numeric token mirror. It expects commands followed by numbers.
    """
    import re
    tokens = re.split(r'([A-Za-z])', path_d)
    out = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if not t:
            i += 1
            continue
        if re.fullmatch(r'[A-Za-z]', t):
            out.append(t)
            i += 1
            # Next chunk contains numbers
            if i < len(tokens):
                nums = tokens[i]
                # Mirror x values. We mirror every odd index in coordinate pairs (x,y).
                numbers = re.findall(r'[-]?\d+(?:\.\d+)?', nums)
                if numbers:
                    mirrored = []
                    # We do not know the exact grouping for each command, so mirror every first of each pair.
                    for idx, num in enumerate(numbers):
                        val = float(num)
                        if idx % 2 == 0:  # x
                            val = 2 * x_axis - val
                        mirrored.append(f"{val:.2f}")
                    # Rebuild by replacing numbers in order
                    def repl(_):
                        return mirrored.pop(0) if mirrored else _
                    nums_out = re.sub(r'[-]?\d+(?:\.\d+)?', repl, nums)
                    out.append(nums_out)
                else:
                    out.append(nums)
            continue
        else:
            out.append(t)
            i += 1
    return "".join(out)

def _grid_lines(w: int, h: int, Hu: float) -> str:
    """Draw faint horizontal guides at landmark positions and a vertical center line."""
    ys = [1.0*Hu, 2.5*Hu, 3.5*Hu, 4.25*Hu, 6.5*Hu, 8.8*Hu]
    cx = w / 2.0
    parts = [f'<line x1="{cx:.2f}" y1="0" x2="{cx:.2f}" y2="{h:.2f}"/>' ]
    for y in ys:
        parts.append(f'<line x1="0" y1="{y:.2f}" x2="{w:.2f}" y2="{y:.2f}"/>')
    return "\n    ".join(parts)
