# Common Assets

Shared resources used by both phases live here:

- `calib/calib.yaml` – canonical intrinsics (`K` + `D`) used as a fallback by both Phase A and Phase B.
- `config/config_example.yaml` – template configuration; copy and tweak for specific deployments.
- `extrinsics/` – drop shared world→camera transforms (e.g., `T_WC.yaml`) when both phases operate from the same camera pose.

When adding new shared data, document it here and keep phase-specific artefacts inside `phase_a/` or `phase_b/`.

For the roll-tracking workflow that consumes these shared assets, see `phase_b/README.md`.

## Multi-camera management

- Keep per-device extrinsics files alongside the canonical defaults, for example:
  - `common/extrinsics/T_WC_webcam.yaml`
  - `common/extrinsics/T_WC_phone.yaml`
  - `common/extrinsics/T_WC_crane_cam.yaml`
- The helper command (see `phase_b/README_phase_b_v2.md` or `PTL24_MARKER_RUN_COMMANDS.md`) can regenerate `common/extrinsics/T_WC.yaml` by specifying HEIGHT/PITCH/YAW/ROLL. Use this when a camera mount changes.
- Both Phase A and Phase B runners accept `--camera common/calib/<file>.yaml` and `--extrinsics common/extrinsics/<file>.yaml`, so keeping these shared assets up to date ensures every phase reports world-frame poses consistently.
