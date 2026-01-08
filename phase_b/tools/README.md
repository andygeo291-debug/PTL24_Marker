# Phase B Tools

## Basler ROI run (baseline)
```bash
python3 -m phase_b.v2.phase_b_tags_v2 \
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
  --debug-metrics runs/basler_roi960x720/debug_metrics.csv \
  --save-poses runs/basler_roi960x720/poses.csv \
  --ransac --adapt --ransac-iters 15
```

## Run summary helper
```bash
python3 phase_b/tools/summarize_run.py \
  --debug-csv runs/basler_roi960x720/debug_metrics.csv \
  --poses-csv runs/basler_roi960x720/poses.csv \
  --cmd runs/basler_roi960x720/run.cmd \
  --out-md runs/basler_roi960x720/summary.md
```
