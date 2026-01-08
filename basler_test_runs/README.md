# Basler Test Runs

This folder stores Basler test suites created by `tools/run_basler_pose_tests.sh`.

## Run numbering

Each run creates a new directory named:

`basler_run_0001_YYYYMMDD_HHMMSS`

The script scans existing `basler_run_*` folders and increments the number.

## How to run

From repo root:

```bash
tools/run_basler_pose_tests.sh
```

Optional: override the base folder (must stay inside the repo):

```bash
RUN_BASE=basler_test_runs tools/run_basler_pose_tests.sh
```

## Output layout

Each run directory contains:

- `terminal.log` (stdout/stderr from the full run)
- `run_cmd.txt` (exact commands executed)
- `quick_checks/` (30-frame tests)
- `spike_on/` (300-frame test, spike rejection enabled)
- `spike_off/` (300-frame test, spike rejection disabled)
- `summary/MEETING_SUMMARY.md`
- `summary/meeting_table.csv`
