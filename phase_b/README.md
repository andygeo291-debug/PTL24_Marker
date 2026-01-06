# Phase B – Marker-Based Pose Tracking

This module holds the Phase B prototype for estimating the 6‑DoF pose of cylindrical paper rolls using an AprilTag rig. Phase A (`PT24_MARKER/`) remains unchanged; all Phase B assets live under `phase_b/`. For a supervisor-facing narrative, see [`EXPLANATION.md`](EXPLANATION.md).

### Phase B variants: v1 vs v2

- **v1** – original implementation (unchanged in `phase_b/v1/`), still shipped for regressions, legacy experiments, and simple comparisons.
- **v2** – refactored runner (`phase_b/v2/phase_b_tags_v2.py`) that adds v1-compat mode, weighted SE(3) fusion, adaptive RANSAC, HUD improvements, and benchmark logging.
- Detailed v2 documentation, validation workflow (S1/S2/S3), and tooling live in [`README_phase_b_v2.md`](README_phase_b_v2.md).
- For a consolidated command cheat sheet (setup, multi-camera extrinsics, validation commands), consult `../PTL24_MARKER_RUN_COMMANDS.md`.

## Why Off-Centre Tags

Large rolls often leave a lifting hole in the centre of the top cap, so no material exists for a tag. The rig therefore uses off-centre single tags or three-tag annuli on the caps, combined with a dense barrel ring, to maintain observability as the roll rotates.

## Printing Guidance

- Match tag size to curvature: use the smaller ring sizes for small radii to avoid warping.
- Print on matte stock; laminate only if the surface stays non-glossy.
- Wipe rolls clean before mounting to reduce specular glare under warehouse lighting.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install opencv-python numpy pupil-apriltags pyyaml
```

Populate `calib/calib.yaml` with your camera intrinsics (keys `K`/`D` or OpenCV YAML format). Example rig definitions are in `rigs/`.

## Run (webcam example)

```bash
cd phase_b
python phase_b_tags.py --camera calib/calib.yaml --rig rigs/cyl_small.yaml --video 0 --family tag36h11 --axis-len 0.2
```

The script opens a live window with fused cylinder axes and logs the tag IDs used each frame.
If `--camera` is omitted, the tool falls back to `../common/calib/calib.yaml` when available.

## World-frame Output & Logging

- Provide world-to-camera extrinsics via `--extrinsics`, e.g. `common/extrinsics/T_WC.yaml`. The YAML can contain either `T_WC` or `T` with a 4×4 matrix.
- Enable CSV logging with `--save-poses phase_b/poses.csv`. The file appends rows with:
  - `timestamp`, `frame`, `used_ids`, `decision_margins`
  - Camera-frame pose (`rvec_cam_*`, `tvec_cam_*`)
  - World-frame pose (`rvec_world_*`, `tvec_world_*`) when extrinsics are supplied
  - Cylinder tilt angles (`tilt_cam_deg`, `tilt_world_deg`)
- Use `--print-tilt` to print per-frame tilt angles (camera +Z to cylinder +Z, and world +Z when extrinsics are present).

Example runs:

```bash
# Camera-frame only with live tilt readout
python phase_b/phase_b_tags.py \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --print-tilt

# Include world-frame pose and CSV logging
python phase_b/phase_b_tags.py \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --video 0 \
  --extrinsics common/extrinsics/T_WC.yaml \
  --save-poses phase_b/poses.csv \
  --print-tilt
```

## Robust Fusion (RANSAC)

Enable `--ransac` to filter outlier tag poses before SE(3) averaging. Tunable parameters:
- `--ransac-iters` – number of RANSAC iterations (default 60).
- `--ransac-trans` – translation inlier threshold in metres (default 0.05).
- `--ransac-rot` – rotation inlier threshold in degrees (default 5.0).

With RANSAC active, logs show `inliers=<count>/<total>` and CSV/streaming outputs reflect the consensus tag IDs and decision margins.

## Live Pose Streaming (UDP)

Use `--stream-udp HOST:PORT` to emit per-frame JSON packets to a crane controller (rate capped by `--stream-rate-hz`, default 30 Hz). Payload schema:

```json
{
  "ts": 1697040000.123,
  "frame": 42,
  "used_ids": [100, 101, 103],
  "decision_margins": [72.5, 68.4, 70.1],
  "cam": {
    "t_m": [0.12, 0.34, 1.05],
    "rvec": [0.01, 0.20, -0.03],
    "quat_xyzw": [0.02, 0.10, -0.01, 0.99]
  },
  "world": {
    "t_m": [2.45, -0.10, 1.05],
    "rvec": [-0.02, 0.25, -0.01],
    "quat_xyzw": [0.01, 0.12, -0.02, 0.99]
  },
  "tilt_cam_deg": 12.4,
  "tilt_world_deg": 11.8
}
```

`world` and `tilt_*` entries appear only when extrinsics and/or `--print-tilt` are provided. Use `phase_b/udp_receive_pose.py --port 6006` as a simple receiver to inspect the stream.

## Limitations

- Requires the printed AprilTag rig; rolls without tags are not observable.
- Assumes precise tag placement to match the provided YAML transforms.
- Sensitive to poor calibration or strong reflections.

## Tooling and validation overview

- `phase_b/tools/compare_poses.py` – RMS comparison between two pose CSVs (e.g., v1 vs v2) to quantify regressions.
- `phase_b/tools/analyze_metrics.py` – parses `debug_metrics.csv` (produced via `--bench`) to plot FPS histograms and tilt jitter over time.
- `phase_b/tools/archive_validation_run.py` – copies the latest pose CSV, debug metrics, and figure directory into `phase_b/validation/<scenario>` (S1 jitter, S2 sweep, S3 long run).
- `phase_b/tools/cleanup_s2_sweep.py`, `augment_poses.py`, and `udp_receive_pose.py` round out the workflow for resetting scenario folders, adding Euler angles, and inspecting live streams.
- See `README_phase_b_v2.md` for specific commands covering S1/S2/S3 validation runs and `PTL24_MARKER_RUN_COMMANDS.md` for a master list of all tooling invocations.

Phase C will blend YOLO-based roll detection with geometric fitting, removing the need for markers once training data is available





# ============================================
# 🔧 1. SET UP ENVIRONMENT
# ============================================
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install numpy opencv-python pandas matplotlib pupil-apriltags pyyaml

# ============================================
# 🧭 2. CREATE EXTRINSICS FILE (height / pitch)
# ============================================
# Adjust HEIGHT and PITCH according to your camera setup.
# Example: HEIGHT=0.9 (m), PITCH=-60 (deg)
HEIGHT=0.86 PITCH=-26 python - <<'PY'
import math, pathlib, os
height=float(os.environ["HEIGHT"])
pitch_deg=float(os.environ["PITCH"])
pitch=math.radians(pitch_deg)
c,s=math.cos(pitch),math.sin(pitch)
data=[1,0,0,0, 0,c,-s,s*height, 0,s,c,-c*height, 0,0,0,1]
path=pathlib.Path("common/extrinsics/T_WC.yaml")
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text("%YAML:1.0\n---\nT_WC:\n rows:4\n cols:4\n data:[\n"+",\n".join(f" {v:.6f}"for v in data)+"\n ]\n")
print(f"✅ extrinsics → {path}")
PY

# ============================================
# 🚀 3. RUN PHASE B (pose estimation + logging)
# ============================================
rm -f phase_b/poses.csv

python -m phase_b.v1.phase_b_tags \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --save-poses phase_b/poses.csv \
  --params phase_b/params.yaml \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --max-tilt-jump-deg 15 \
  --axis-len 0.1 \
  --video 0 \
  --print-tilt

# video 0: external webcam | 1: MacBook cam | 2: iPhone cam (via Camo, etc.)
# 💡 add   --ignore-ids "101,202"   to skip noisy tags.

# ============================================
# 🧩 4. CONVERT poses.csv → ADD EULER COLUMNS
# ============================================
python - <<'PY'
import math, sys, numpy as np, pandas as pd, cv2
from pathlib import Path
src=Path("phase_b/poses.csv"); dst=Path("phase_b/poses_with_euler.csv")
if not src.exists(): sys.exit("❌ run Phase B first")

df=pd.read_csv(src)
has_quat={"qx","qy","qz","qw"}.issubset(df.columns)

def quat_to_R(qx,qy,qz,qw):
    n=math.sqrt(qx*qx+qy*qy+qz*qz+qw*qw)
    if n==0: return np.eye(3)
    qx,qy,qz,qw=[q/n for q in (qx,qy,qz,qw)]
    xx,yy,zz=qx*qx,qy*qy,qz*qz; xy,xz,yz=qx*qy,qx*qz,qy*qz
    wx,wy,wz=qw*qx,qw*qy,qw*qz
    return np.array([[1-2*(yy+zz),2*(xy-wz),2*(xz+wy)],
                     [2*(xy+wz),1-2*(xx+zz),2*(yz-wx)],
                     [2*(xz-wy),2*(yz+wx),1-2*(xx+yy)]])

def euler_zyx(R):
    sy=math.sqrt(R[0,0]**2+R[1,0]**2)
    if sy<1e-6:
        yaw,pitch,roll=math.atan2(-R[0,1],R[1,1]),math.atan2(-R[2,0],sy),0
    else:
        yaw,pitch,roll=math.atan2(R[1,0],R[0,0]),math.atan2(-R[2,0],sy),math.atan2(R[2,1],R[2,2])
    return [math.degrees(roll),math.degrees(pitch),math.degrees(yaw)]

roll,pitch,yaw=[],[],[]
if has_quat:
    for qx,qy,qz,qw in df[["qx","qy","qz","qw"]].itertuples(index=False,name=None):
        R=quat_to_R(qx,qy,qz,qw); r,p,y=euler_zyx(R)
        roll.append(r); pitch.append(p); yaw.append(y)
else:
    for rvx,rvy,rvz in df[["rvec_cam_x","rvec_cam_y","rvec_cam_z"]].to_numpy(dtype=float):
        R,_=cv2.Rodrigues(np.array([rvx,rvy,rvz]).reshape(3,1))
        r,p,y=euler_zyx(R)
        roll.append(r); pitch.append(p); yaw.append(y)

df["roll_deg"],df["pitch_deg"],df["yaw_deg"]=roll,pitch,yaw
dst.parent.mkdir(parents=True,exist_ok=True)
df.to_csv(dst,index=False)
print(f"✅ Euler CSV → {dst}")
PY

# ============================================
# 📈 5. PLOT EULER + TILT ANGLES
# ============================================
python - <<'PY'
import pandas as pd, matplotlib.pyplot as plt
from pathlib import Path
csv=Path("phase_b/poses_with_euler.csv")
if not csv.exists(): raise SystemExit("❌ Euler CSV missing; run previous step.")
df=pd.read_csv(csv)
cols=[c for c in ("roll_deg","pitch_deg","yaw_deg","tilt_cam_deg") if c in df.columns]
if not cols: raise SystemExit("no angle columns to plot")

plt.figure(figsize=(10,5))
for c in cols: plt.plot(df.index,df[c],label=c)
plt.legend(); plt.xlabel("Frame"); plt.ylabel("Degrees")
plt.title("Phase B Angles"); plt.grid(True); plt.tight_layout()
out="phase_b/poses_with_euler.png"
plt.savefig(out,dpi=150)
print(f"✅ Plot → {out}")
PY





# 0) (optional) activate your venv
source venv/bin/activate

# 1) Ensure Python can treat `phase_b/` as a package
touch phase_b/__init__.py

# 2) Clean any old CSVs
rm -f phase_b/poses.csv phase_b/debug_metrics.csv

# 3) Run the **legacy** path once (sanity check)
python phase_b/phase_b_tags.py \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --save-poses phase_b/poses.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 --min-inliers 3 --max-tilt-jump-deg 15 \
  --axis-len 0.1 --video 2 --print-tilt

# 4) Run **v2** as a module (recommended)
python -m phase_b.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --save-poses phase_b/poses.csv \
   --video 0 \
  --print-tilt


# 1) Run v2 with features ON (weighted fusion + HUD + benchmark)
python -m phase_b.phase_b_tags_v2 \
  --config phase_b/config.yaml \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --save-poses phase_b/poses.csv \
  --use-weighted-se3 --hud --bench --video 0 \
 --print-tilt
