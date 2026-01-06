SHELL := /bin/bash
.ONESHELL:

VENV := venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

CAMERA ?= common/calib/calib.yaml
RIG ?= phase_b/rigs/cyl_paper.yaml
EXTRINSICS ?= common/extrinsics/T_WC.yaml
POSES ?= phase_b/poses.csv
POSES_EULER ?= phase_b/poses_with_euler.csv
VIDEO ?= 0
FAMILY ?= tag36h11
AXIS ?= 0.2

RANSAC_TRANS ?= 0.05
RANSAC_ROT ?= 5
EMA_ALPHA ?= 0.3
MIN_INLIERS ?= 3
MAX_TILT_JUMP_DEG ?= 15

TOL ?= 0

UDP_ADDR ?= 192.168.1.50
UDP_PORT ?= 6006
STREAM_HZ ?= 20

HEIGHT ?= 1.07
PITCH ?= -19

.DEFAULT_GOAL := help

.PHONY: help setup venv_guard install deps extrinsics b_run b_udp euler plot check clean all

help: ## Show available targets
	@echo "PTL24_MARKER Makefile — common tasks"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make setup"
	@echo "  make extrinsics HEIGHT=1.07 PITCH=-19"
	@echo "  make b_run VIDEO=0 AXIS=0.2"
	@echo "  make euler"
	@echo "  make plot"

setup: venv_guard deps ## Create venv and install dependencies

install: setup ## Alias for setup

venv_guard:
	if [ ! -d "$(VENV)" ]; then
		echo "🟡 Creating venv at $(VENV)"
		python3 -m venv $(VENV)
	fi
	$(PY) -V >/dev/null 2>&1 || { echo "❌ Python venv not healthy"; exit 1; }

deps: venv_guard
	echo "🔧 Upgrading pip"
	$(PIP) install --upgrade pip
	if [ -f requirements.txt ]; then
		echo "📦 Installing from requirements.txt"
		$(PIP) install -r requirements.txt
	else
		echo "📦 Installing numpy, opencv-python, pandas, matplotlib, pupil-apriltags"
		$(PIP) install numpy opencv-python pandas matplotlib pupil-apriltags
	fi

extrinsics: venv_guard ## Write T_WC.yaml from HEIGHT (m) and PITCH (deg)
	$(PY) -c "import pathlib; pathlib.Path('$(EXTRINSICS)').parent.mkdir(parents=True, exist_ok=True)"
	HEIGHT=$(HEIGHT) PITCH=$(PITCH) $(PY) -c "import math, os, pathlib; height=float(os.environ['HEIGHT']); pitch_deg=float(os.environ['PITCH']); pitch=math.radians(pitch_deg); c=math.cos(pitch); s=math.sin(pitch); data=[1.0,0.0,0.0,0.0, 0.0,c,-s,s*height, 0.0,s,c,-c*height, 0.0,0.0,0.0,1.0]; payload='\n'.join('    {:.6f}'.format(v) for v in data); lines=['%YAML:1.0','---','T_WC:','  rows: 4','  cols: 4','  data: [',payload,'  ]']; text='\n'.join(lines)+'\n'; path=pathlib.Path('$(EXTRINSICS)'); path.write_text(text); print(f'✅ extrinsics → {path}')"

b_run: venv_guard ## Run Phase B pipeline
	$(PY) phase_b/phase_b_tags.py --camera $(CAMERA) --rig $(RIG) --video $(VIDEO) --family $(FAMILY) --axis-len $(AXIS) --extrinsics $(EXTRINSICS) --save-poses $(POSES) --ransac --ransac-trans $(RANSAC_TRANS) --ransac-rot $(RANSAC_ROT) --ema-alpha $(EMA_ALPHA) --min-inliers $(MIN_INLIERS) --max-tilt-jump-deg $(MAX_TILT_JUMP_DEG) --print-tilt

b_udp: venv_guard ## Run Phase B with UDP stream
	$(PY) phase_b/phase_b_tags.py --camera $(CAMERA) --rig $(RIG) --video $(VIDEO) --family $(FAMILY) --axis-len $(AXIS) --extrinsics $(EXTRINSICS) --save-poses $(POSES) --ransac --ransac-trans $(RANSAC_TRANS) --ransac-rot $(RANSAC_ROT) --ema-alpha $(EMA_ALPHA) --min-inliers $(MIN_INLIERS) --max-tilt-jump-deg $(MAX_TILT_JUMP_DEG) --stream-udp $(UDP_ADDR):$(UDP_PORT) --stream-rate-hz $(STREAM_HZ) --print-tilt

euler: venv_guard ## Convert poses.csv to poses_with_euler.csv
	$(PY) phase_b/tools/augment_poses.py --source $(POSES) --out $(POSES_EULER) --overwrite

plot: venv_guard ## Plot Euler traces
	$(PY) -c "import pandas as pd, matplotlib.pyplot as plt; from pathlib import Path; csv_path = Path('$(POSES_EULER)');
if not csv_path.exists():
    raise SystemExit('poses_with_euler.csv not found. Run `make euler` first.'); df = pd.read_csv(csv_path); cols = [c for c in df.columns if c.endswith('_cam_deg')]; plt.figure(figsize=(10,5)); [plt.plot(df.index, df[col], label=col) for col in cols]; plt.legend(); plt.xlabel('Frame'); plt.ylabel('Degrees'); plt.title('Phase B Euler Angles'); plt.grid(True); plt.tight_layout(); out = Path('phase_b/poses_with_euler.png'); plt.savefig(out, dpi=150); print(f'✅ Plot → {out}')"

check: venv_guard ## Compile-check Python files
	$(PY) -m py_compile phase_b/phase_b_tags.py || true
	if [ -f phase_b/tools/augment_poses.py ]; then $(PY) -m py_compile phase_b/tools/augment_poses.py; fi
	if [ -f phase_b/udp_receive_pose.py ]; then $(PY) -m py_compile phase_b/udp_receive_pose.py; fi
	echo "Python compile check complete."

clean: ## Remove caches/outputs
	rm -rf __pycache__ */__pycache__ .pytest_cache
	find . -name '*.pyc' -delete
	rm -f $(POSES) $(POSES_EULER) phase_b/poses_with_euler.png
	echo "Cleaned caches and generated files."

all: extrinsics b_run euler plot ## Full pipeline (extrinsics → run → euler → plot)

.PHONY: regress
regress: venv_guard ## Run deterministic v1 vs v2 regression comparison
	$(PY) tools/regress_v1_v2.py --camera $(CAMERA) --rig $(RIG) --extrinsics $(EXTRINSICS) --video $(VIDEO) --frames 200 --tolerance $(TOL)
