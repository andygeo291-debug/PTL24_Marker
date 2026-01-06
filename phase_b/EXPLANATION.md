# Phase B Deep Dive – Geometry, Helpers, and Data Products

The Phase B pipeline fuses AprilTag observations into a robust cylinder pose suited for industrial roll handling. This document explains the supporting math, helper functions, stability rules, artefacts, and the role of each file involved in the workflow.

---

## 1. Mathematical Helpers

Phase B leans on a Lie-theoretic toolkit to avoid singularities when fusing poses:

- `skew(v)` – builds the 3×3 skew-symmetric matrix used in cross products and Rodrigues’ formula.  
- `so3_exp(ω)` / `so3_log(R)` – exponential and logarithmic maps between rotation vectors and matrices. These keep rotation averaging well-behaved near 180° flips.  
- `se3_exp(ξ)` / `se3_log(T)` – map between a 6×1 twist (`[ω, v]`) and a full SE(3) transform. The Jacobian (`V`) terms ensure translation is updated consistently with rotation.  
- `avg_poses_SE3(Ts, ws)` – iteratively averages a list of transforms by projecting them into `se3`, weighting residuals, and re-exponentiating. This underpins the fused roll pose.  
- `rot_angle_deg(R)` and `se3_deviation(A, B)` – quick distance metrics used by RANSAC and logging to reason about translation and rotation error simultaneously.  
- Quaternion utilities (`quat_from_R`, `rotation_matrix_to_quaternion`, `continuous_quat`, `slerp`) – maintain a consistent sign to avoid sudden 180° jumps and produce smooth EMA blending.  
- `apply_ema_pose` – applies exponential moving average directly in SE(3): blend translations linearly, blend quaternions via SLERP, rebuild a homogeneous transform.  
- `compute_tilt_deg` – measures tilt of the cylinder axis against a reference (camera/world +Z).  
- `euler_zyx_from_R` – converts the fused rotation matrix into roll/pitch/yaw (ZYX) for CSV logging.

Each helper lives in `phase_b_tags.py` and is unit-free, making it reusable anywhere we manipulate SE(3) poses.

---

## 2. RANSAC Logic

When `--ransac` is supplied, the fusion pipeline performs:

1. **Sampling:** random subsets of at least three tag-derived poses.  
2. **Model hypothesis:** SE(3) transform averaged from the subset.  
3. **Inlier scoring:** compare every candidate pose against the hypothesis; a pose qualifies if translation error ≤ `--ransac-trans` metres **and** rotation error ≤ `--ransac-rot` degrees.  
4. **Retention:** keep all hypotheses that tie for lowest residual; defer to temporal selection (`select_candidate`) to pick the one closest to the last fused pose.  

The process is intentionally conservative—if RANSAC fails (few tags, poor consensus) the code reverts to averaging all detections so motion continues with graceful degradation.

---

## 3. Stability Rules

The fusion output is only as good as the temporal filtering layered on top:

- **Minimum inliers** (`--min-inliers`): if the current inlier count drops below this threshold, status switches to `HOLD_PREV_POSE` and the overlay/log stream uses `last_good_pose`.  
- **Tilt spike rejection:** compute tilt in the camera frame and reject updates where the change exceeds `--max-tilt-jump-deg`; this catches corruption when a new tag briefly appears on the edge of view.  
- **Last-good pose store:** all downstream consumers (overlay, logging, UDP) reference `last_good_pose`, ensuring we never publish a pose that the stability filter rejected.  
- **EMA smoothing:** optional SE(3) exponential moving average reduces jitter without biasing heavily; `--ema-alpha` ∈ [0, 1] controls responsiveness.  
- **Quaternion continuity:** flips sign to keep quaternions in the same hemisphere, avoiding double-cover artefacts that would trigger fictitious spikes in downstream filters.

Together these rules allow the tracker to ride out short occlusions, motion blur, or brief mis-detections without destabilising the crane guidance loop.

---

## 4. Overlay Policy

`draw_from_last_good` renders axes and tag summaries from `last_good_pose` rather than the frame’s raw candidate. Benefits:

- Prevents the overlay from “snapping” to outliers that were rejected by stability checks.  
- Keeps a steady reference while status is `HOLD_PREV_POSE` or `REJECT_SPIKE`.  
- Displays status text (OK/HOLD/NO_POSE) so operators immediately know why the pose is frozen.  
- Adjust `--axis-len` to tune visual scale without impacting smoothing or logging.

---

## 5. File Purposes

- **`phase_b/phase_b_tags.py`** – orchestrates detection, rig lookup, pose fusion, filtering, overlay rendering, CSV writes, and UDP streaming. CLI flags expose most tuning knobs, including fallback calibration (`common/calib`), extrinsics, and logging paths.  
- **`phase_b/tools/augment_poses.py`** – reads `poses.csv`, converts available Rodrigues vectors to ZYX Euler angles, and writes a companion CSV for plotting or analytics. Handles camera/world frames independently.  
- **`phase_b/rigs/*.yaml`** – define rig geometry. Each tag stores `T_tag_to_cyl` so the code can link detector output to the shared cylinder frame. Modify these files when you change tag layouts or dimensions.  
- **`phase_b/params.yaml`** – optional parameter bundle consumed when `--params` is provided; acts as a preset for camera index, thresholds, EMA settings, and logging defaults. Documented in the Phase B README.  
- **`phase_b/udp_receive_pose.py`** – lightweight UDP sink for debugging the live stream.  
- **`common/extrinsics/T_WC.yaml`** – world-to-camera extrinsics generator used in the runbook; ensures CSV v2 emits world tilt whenever available.

---

## 6. Data Products

- **`poses.csv` (schema v2)** – authoritative record of fused camera-frame poses. Quaternions (`qx,qy,qz,qw`) and Euler angles (`roll_deg,pitch_deg,yaw_deg`) are consistent because they stem from the same rotation matrix. `used_tag_ids` and `decision_score` simplify downstream QA.  
- **`poses_with_euler.csv`** – optional augmentation that adds Euler columns derived from Rodrigues vectors (useful when comparing against legacy logs).  
- **`poses_roll_pitch_yaw.png`** – quick-look plot of camera-frame Euler angles; generated by the README commands for regression snapshots.  
- **UDP stream** – JSON payload consumed by crane controllers or monitoring dashboards; includes status flags and, when available, world-frame equivalents.

Inspect these artefacts after every run to confirm control inputs remain within expected bounds and to detect sensor drift early.

---

## 7. Known Trade-offs & Environmental Sensitivities

- **Decision margin dependence:** AprilTag’s `decision_margin` drops under harsh lighting or motion blur. Because we weight poses by this margin, low values reduce influence—even if tags are still technically “detected.”  
- **Occlusion tolerance:** The rig is designed to keep at least three tags visible during typical crane motion, but prolonged occlusion still triggers `HOLD_PREV_POSE`.  
- **Calibration accuracy:** Intrinsic and extrinsic errors feed directly into pose bias. Re-run calibration when lenses or camera mounts change.  
- **Rig compliance:** Paper or foam surfaces can flex; ensure tags stay flat or adjust the rig YAML to match measured offsets.  
- **Network latency:** UDP streaming is fire-and-forget; consider redundancy or heartbeat monitoring when integrating with safety-critical systems.

---

## 8. Putting It All Together

1. Generate or verify calibration (`common/calib/calib.yaml`) and extrinsics (`common/extrinsics/T_WC.yaml`).  
2. Confirm rig YAML matches the printed asset.  
3. Run `phase_b_tags.py` with the recommended flags from the README.  
4. Monitor the terminal (status logs), overlay window (axes, status text), and UDP receiver if attached.  
5. Inspect `poses.csv` and optional plots to validate stability before handing the pose stream to downstream automation.  

For implementation notes and inline commentary, explore the docstrings and comments embedded directly in `phase_b_tags.py` and `tools/augment_poses.py`.
