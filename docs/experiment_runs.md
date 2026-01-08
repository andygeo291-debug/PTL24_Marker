# Experiment runs

This repo uses one-run-per-folder for Basler Phase B v2 experiments.

## Run the Basler script
From repo root:
```bash
scripts/run_basler_phaseb.sh
```

Override settings with environment variables, e.g.:
```bash
FPS=20 EXPOSURE_US=20000 RANSAC_ITERS=30 scripts/run_basler_phaseb.sh
```

Provide an optional run tag prefix as the first argument:
```bash
scripts/run_basler_phaseb.sh my_custom_tag
```

## Run-dir from Phase B v2
Phase B v2 can create its own run folder without the wrapper script:
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
  --save-run --run-name basler_roi_test \
  --camera-backend basler \
  --basler-serial <SERIAL> \
  --basler-name <NAME> \
  --width 960 --height 720 --fps 15 \
  --basler-pixel-format Mono8 \
  --basler-exposure-us 15000 \
  --basler-gain 0 \
  --basler-offset-x 320 --basler-offset-y 200 \
  --basler-interpacket-delay 3500 \
  --basler-timeout-ms 1000 \
  --rig phase_b/rigs/cyl_dotec.yaml \
  --camera common/calib/basler_static_960x720_offx320_offy200_mono8.yaml \
  --debug-metrics-out debug_metrics.csv \
  --poses-out poses.csv \
  --ransac --adapt --ransac-iters 15 \
  --no-hud --quiet-apriltag-stderr
```

## Output layout
The script creates a run folder under `runs/<RUN_TAG>/` with:
- `poses.csv`
- `debug_metrics.csv`
- `run.log`
- `run.cmd`
- `summary.txt`

Phase B v2 `--save-run` creates:
- `run_cmd.txt`
- `run_meta.json`
- `run_header.json`
- `inputs/` (copied rig/calib/config/extrinsics)

## Reproduce a run
Copy/paste the exact command from `runs/<RUN_TAG>/run.cmd`, or run it directly:
```bash
bash runs/<RUN_TAG>/run.cmd
```
