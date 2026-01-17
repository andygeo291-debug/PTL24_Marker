# Architecture Overview (Phase B v2)

## What Phase B v2 is
Phase B v2 is the current, production-oriented pipeline for AprilTag-based
6-DoF pose estimation of the cylindrical rig. It keeps the v1 detection and
camera utilities but adds structured logging, run metadata, and per-frame
timing/quality metrics needed for reporting.

## System boundaries and interfaces
Inputs:
- Camera frames (Basler GigE or OpenCV backend)
- Rig definition YAML (`phase_b/rigs/*.yaml`)
- Camera calibration YAML (`common/calib/*.yaml`)
- Optional extrinsics YAML (world-to-camera)

Outputs:
- `poses.csv` (rvec/tvec + tilt values per frame)
- `debug_metrics.csv` (timings, tag counts, reject reasons)
- Optional HUD/overlay window
- Optional UDP pose stream (for downstream consumers)

## High-level data flow
1) Capture a frame from the camera backend.
2) Preprocess (grayscale, optional undistort).
3) Detect AprilTags and compute per-tag poses.
4) RANSAC/filtering and SE(3) fusion.
5) Quality/spike gate selects OK/HOLD/REJECT outcomes.
6) Write outputs (poses.csv + debug_metrics.csv) and emit bench logs.

## Phase B v2 vs other phases
- Phase A: upstream experiments/prototypes (not the production Basler pipeline).
- Phase B v1: legacy pipeline and helper utilities (detector setup, capture, CSV formats).
- Phase B v2: current production pipeline with richer logging and stability metrics.
- Phase C: downstream analysis/reporting workflows that consume Phase B outputs.
