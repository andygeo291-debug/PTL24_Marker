# Phase B v2 – Geometry-Assisted Pose Estimation

Phase B v2 delivers a configurable, provenance-aware pipeline for estimating the 6‑DoF pose of cylindrical rolls from AprilTag rigs. It keeps the proven v1 geometry stack while adding centralized config, weighted SE(3) fusion, HUD/debug outputs, and micro-benchmarking. Compared to v1, v2 is easier to audit, instrument, and extend toward Phase C’s learning-based fusion.

---

## 1. Overview

**What it is.** Phase B v2 is the geometry-assisted pose layer of PTL24_MARKER. It ingests AprilTag detections, filters them for consistency, and reports a fused cylinder pose in real time.

**Goal.** Compute a stable camera→cylinder transform (translation + rotation) so downstream systems can position the roll in space with centimeter/degree accuracy.

**Why v2.**
- Centralized YAML + CLI override keeps deployments reproducible.
- Weighted fusion and provenance headers improve numeric robustness.
- HUD/debug metrics give instantaneous feedback for field ops.

---

## 2. Robustness & Structure

- **Inherited strengths from v1**
  - Modular stages: capture → detect → per-tag PnP → RANSAC → SE(3) fusion → EMA.
  - SE(3) log/exp averaging keeps rotation+translation tightly coupled.
  - EMA smoothing and tilt spike rejection prevent jitter.
- **Why configuration hygiene matters**
  - Parameter drift previously required manual CLI tweaks; YAML ensures consistent provisioning.
  - Provenance stamping (`# {...}` header) records commit hashes, SHA-256 fingerprints, and runtime knobs for every CSV artifact.
  - Frame conventions (camera frame, cylinder frame, world frame) are now documented and enforced.
- **Diagram**

  ![Pipeline overview](diagram.png)

- **Reliability guardrails**
  - RANSAC consensus with adaptive thresholds (`ransac_trans`, `ransac_rot`).
  - Minimum inlier count before pose acceptance.
  - Tilt jump guardrails (`max_tilt_jump_deg`) to reject discontinuities.
  - Runtime sanity asserts on tag IDs, rig geometry, and camera calibration presence.

---

## 3. Accuracy & Numerical Stability

**Weighted SE(3) fusion**  
Each tag’s pose earns a weight from reprojection error, pixel area, and viewing angle. High-confidence tags influence the fused pose more strongly.

\[
\hat{T} = \exp\!\Big(\sum_i w_i \log(T_i \hat{T}^{-1}_{\text{prev}})\Big)\hat{T}_{\text{prev}}
\]
*Plain English:* “Shift the previous pose by a weighted blend of per-tag pose deltas expressed in tangent space.”

**Intuition:**
- `log` maps homogeneous transforms into 6D twist vectors.
- `exp` maps the blended twist back into SE(3).
- Using the previous fused pose as the reference keeps updates local and well-conditioned.

**RANSAC.**
- Samples pose subsets, estimates a candidate, scores inliers by translation + rotation error.
- Adaptive thresholds from config allow conservative or aggressive behavior depending on the environment.
- Rejects spurious detections before weighted fusion sees them.

**Geometric priors.**
- Known cylinder radius and axis ensure tag-to-cylinder transforms remain consistent.
- Cap vs ring tags encode axial vs circumferential placement; deviations trigger health warnings.

---

## 4. Temporal Filtering

- **Exponential Moving Average (EMA)**
  - Simple low-pass on translation + quaternion.
  - Zero-lag update, easy to tune with `ema_alpha`.
  - Works best when motion is slow and sensing is dense.
- **Extended Kalman Filter (EKF) – future option**
  - State vector example: \([p, v, q, \omega]\) where \(p\) = position, \(v\) = velocity, \(q\) = orientation quaternion, \(\omega\) = angular velocity.
  - Can predict dynamics during occlusions and blend IMU data.
  - Requires accurate motion/measurement models; see Phase C plan.

---

## 5. Outlier Handling & Health Indicators

- **Rig consistency checks**
  - Verifies detected tag IDs exist in `phase_b/rigs/*.yaml`.
  - Confirms perimeter spacing and tag size match rig spec.
  - Enforces minimum inliers before publishing new poses.
- **HUD overlay (toggle via YAML or `--hud`)**
  - FPS, visible tags, inliers, mean reprojection error, and tilt (deg).
  - Axis visualization from fused pose.
  - `--no-overlay` disables all drawing when video throughput matters.
- **`debug_metrics.csv`**
  - Logs per-frame health stats with a provenance header:
    - `t`, `fps`, `n_visible`, `n_inliers`, `mean_reproj`, `ransac_score`, `weight_min/max`, `tilt_deg`.
    - Additional spike diagnostics when tilt jump guard trips: `spike_delta_trans_m`, `spike_delta_rot_deg`, `spike_trans_thresh_m`, `spike_rot_thresh_deg`, `spike_ref_age_frames`, `spike_ref_frame_idx`.
  - Useful for regression plots, trend analysis, and anomaly detection.
  - Health auto-reset: `runtime.health.spike_reset_after` (default 10) resets the spike reference after consecutive rejections to avoid lockout.

---

## 6. Camera, Calibration & Imaging

- **Calibrations**
  - Intrinsics (`common/calib/calib.yaml`): focal length, principal point, distortion coefficients.
  - Extrinsics (`common/extrinsics/T_WC.yaml`): world→camera transform for global reporting.
  - Accuracy depends on precise calibration; re-run whenever optics change.
- **Distortion models**
  - OpenCV pinhole with radial/tangential terms; ensure the YAML matches the lens.
  - For rolling shutter cameras, consider per-frame rectification.
- **Imaging considerations**
  - Lighting: avoid reflective hotspots; diffuse lighting yields cleaner edges.
  - Exposure: set manual exposure to reduce flicker and maintain consistent detection margins.
  - Rolling shutter: motion blur can elongate tags; apply ROI cropping or motion blur detection if needed.
  - Optional ROI optimization: focus detection on known tag areas to save cycles.

---

## 7. Performance & Real-Time Optimizations

- **Threading model**
  - Capture thread reads frames into a ring buffer.
  - Detection + fusion operate sequentially on the latest buffered frame.
  - Rendering (HUD/axes) runs only if overlay enabled.
- **Optimizations**
  - Memory reuse for detection buffers and pose arrays.
  - Skipping render/HUD when headless to cut GPU/CPU work.
  - Potential use of `numba` or C++ extensions for SE(3) log/exp and weighting loops.
  - Batch the weighted log/exp computations to leverage SIMD.
- **Bench log example**

  ```text
  [bench] over 60 frames total=7.5ms capture=1.3ms detect=1.4ms pnp=1.1ms ransac=0.9ms fuse=1.2ms render=1.6ms
  ```

  *Plain English:* “Average frame time is 7.5 ms; detection costs 1.4 ms, rendering costs 1.6 ms, etc.”

---

## 8. Experimental Validation

- **Test plan dimensions**
  - Range: 0.3 m → 2.5 m standoff distances.
  - Pitch/roll: evaluate ±30° orientation.
  - Lighting: bright factory, dim lab, directional spot.
  - Occlusion: partial tag coverage, finger occlusions.
  - Motion: slow sweep, fast spin, stop-and-go.
- **Metrics**
  - Pose jitter (std dev) in translation/rotation.
  - Drift over time (cumulative error w.r.t. ground truth).
  - Frame validity rate (percentage of frames with fresh pose).
  - FPS distribution (min/avg/max).
- **Automation**
  - Playback recorded sequences, log debug metrics, summarize in tables.
  - Example summary columns: scenario, mean tilt error, inlier ratio, bench ms/frame.

---

## 9. Visualization & Debugging

- Optional plots:
  - Euler angle trends from `poses.csv`.
  - Tilt vs time to monitor roll stability.
  - Scatter plots of reprojection error per tag.
- Future visual aids:
  - Uncertainty ellipsoids around cylinder axis.
  - Per-tag ray rendering to highlight which detections drive the pose.
  - Heatmap of weight distribution for quality analysis.

---

## 10. Rig & Model Extensions

- Multi-rig support
  - Add YAML entries under `phase_b/rigs/`.
  - Each rig defines tag IDs, sizes, and transforms, enabling quick swaps.
- Cylinder radii variations
  - Update `radius_m`/`length_m`; geometry helpers auto-adapt.
- Partial visibility
  - Weighted fusion lets a single high-quality tag drive pose updates.
  - EMA + “hold last good pose” ensures continuity when tags temporarily disappear.

---

## 11. Readiness for Phase C (YOLO + Geometry Fusion)

- Clean pose outputs with timestamps and optional covariance placeholders.
- Feed to Phase C’s object detector for gated association (matching vision boxes to pose tracks).
- Suggested data structure:

  ```python
  PoseCamCylinder = {
      "T_WC": T_world_to_cylinder,
      "cov": Sigma_pose,
      "timestamp": t_pose,
  }

  Detections = [
      { "class": "roll", "score": 0.93, "bbox": [x, y, w, h] },
      ...
  ]
  ```

- Phase B v2 ensures pose latency and logging are consistent, simplifying multi-sensor fusion.

---

## 12. Summary Table: Improvements from v1 to v2

| Feature | v2 Improvement |
| --- | --- |
| Configuration | Central YAML with CLI overrides and provenance headers |
| SE(3) Fusion | Weighted log/exp averaging with quality-driven weights |
| Observability | HUD overlay + `debug_metrics.csv` for per-frame diagnostics |
| Benchmarks | StageTimer with periodic timing summaries |
| Provenance | Git hash + SHA-256 stamps embedded in CSV outputs |
| Modularity | Versioned package structure (`phase_b.v1`, `phase_b.v2`) |
| Health Monitoring | Weight extrema, inlier count, tilt logging |

---

## 13. Next Steps (Phase C)

- Integrate EKF or complementary filter for motion prediction and sensor fusion.
- Add explicit cylinder surface constraints (project fused pose onto radius/axis manifold).
- Fuse YOLO detections with geometric pose to handle tag dropouts and dynamic scenes.
- Expand benchmarking harness to cover GPU offload and network streaming latencies.

---

## For New Contributors

1. **Start here:** `phase_b/v2/phase_b_tags_v2.py` – main loop, config ingestion, HUD, benchmarking.
2. **Quality weighting:** `phase_b/v2/quality.py` – tag confidence heuristic and softmax.
3. **Pose fusion:** `phase_b/v2/se3_fuse.py` – SE(3) log/exp wrappers and weighted averaging.
4. **Config/provenance:** `phase_b/v2/utils_config.py` – YAML loading, git/hash computation.
5. **Logging & HUD:** `phase_b/v2/debug_log.py` – CSV logger and overlay helper.
6. **Benchmarking:** `phase_b/v2/bench.py` – StageTimer implementation.

Read the README commands for running v1/v2; then follow the debug metrics CSV and HUD to get a feel for real-time behavior before diving into extensions.
