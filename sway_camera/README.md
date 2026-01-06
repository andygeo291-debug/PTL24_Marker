# Sway Camera Toolkit

The sway-mounted camera rides on the moving crane arm, so its pose depends on the sway position $s$. We model the camera pose as
\[
T_{WC}(s) = \begin{bmatrix} R_{WC}(s) & p_0 + s\,\mathbf{d}_{\text{sway}} + p_{\text{offset}} \\ 0 & 1 \end{bmatrix},
\]
where $p_0$ is a reference point on the sway axis, $\mathbf{d}_{\text{sway}}$ is a unit direction vector, and $p_{\text{offset}}$ captures mounting offsets.

## Quick Start

### Step 1: Motion logging
```bash
python -m sway_camera.apps.motion_logger \
  --cam 0 \
  --tag-family tag36h11 \
  --tag-size 0.10 \
  --ref-id 3 \
  --out-csv sway_camera/data/sway_poses_tag3.csv
```
- Move the camera along a roughly straight path while Tag 3 stays visible.
- Tag 3 (family tag36h11, ID 3, size 0.10 m) defines the proxy world frame in the lab.

### Step 2: Fit the sway axis
```bash
python -m sway_camera.apps.fit_sway_axis \
  --csv sway_camera/data/sway_poses_tag3.csv \
  --use-absolute \
  --out sway_camera/data/sway_model.yaml
```
- The fitter extracts $p_0$ (mean position) and $\mathbf{d}_{\text{sway}}$ (principal direction).
- $\mathbf{d}_{\text{sway}}$ is a unit 3D vector that aligns with the motion.

### Step 3: Generate $T_{WC}(s)$
```bash
python -m common.extrinsics.make_extrinsics_sway \
  --sway-model sway_camera/data/sway_model.yaml \
  --sway-pos 0.25 \
  --cam-offset-x 0.0 --cam-offset-y 0.0 --cam-offset-z 0.0 \
  --yaw-deg 0.0 --pitch-deg -20.0 --roll-deg 0.0 \
  --out common/extrinsics/T_WC.yaml
```
- Produces a Phase-B-compatible extrinsics file that encodes the sway camera pose for the chosen $s$.

### Step 4: Run Phase B v2 with sway extrinsics
```bash
python -m phase_b.v2.phase_b_tags_v2 \
  --camera common/calib/calib.yaml \
  --rig phase_b/rigs/cyl_paper.yaml \
  --extrinsics common/extrinsics/T_WC.yaml \
  --video auto \
  --width 1920 --height 1080 --fps 30 \
  --save-poses phase_b/v2/poses_sway_test.csv \
  --ransac --ransac-trans 0.05 --ransac-rot 5 \
  --ema-alpha 0.3 \
  --min-inliers 3 \
  --max-tilt-jump-deg 15 \
  --print-tilt
```
- This run uses the sway-camera extrinsics to process live data in Phase B v2.
- Compare the world-frame roll across different sway positions to ensure consistency.

## When the real crane arrives
- The fixed AprilTag board on the crane structure will define the world frame instead of Tag 3.
- Repeat motion logging and sway-axis fitting using the actual sway motion profile.
- PTL23 will evaluate $T_{WC}(s)$ online using the same $(p_0, \mathbf{d}_{\text{sway}}, p_{\text{offset}})$ model plus encoder-reported sway positions.
