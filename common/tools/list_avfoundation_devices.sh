#!/usr/bin/env bash
set -euo pipefail

echo "Listing AVFoundation devices via ffmpeg (macOS):"
ffmpeg -f avfoundation -list_devices true -i "" >/dev/null 2>&1 || true
cat <<'EOF'

Picking the index:
- The camera index is the number in square brackets next to the video device in the ffmpeg list.
- For Logitech C920, look for an entry like "[0] Logitech HD Pro Webcam C920" and use --video 0.
- If you see only "Continuity Camera" entries, you're pointed at the iPhone; switch USB devices or adjust --video.
EOF
