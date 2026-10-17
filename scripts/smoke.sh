#!/usr/bin/env bash
# Smoke test: make a tiny animated film end to end with the system voice (no model downloads), headless.
# Used by CI; runs anywhere filmwright, ffmpeg, espeak-ng and a Playwright Chromium are installed.
set -euo pipefail
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

filmwright new "$WORK/film" --mode explainer --format story --voice system --music upbeat \
  --outputs hd,square,stems --disclosure metadata --yes
python - "$WORK/film/explainer/stories.json" <<'PY'
import json, sys
p = sys.argv[1]; stories = json.load(open(p)); json.dump(stories[:1], open(p, "w"))   # one film is enough
PY
filmwright storyboard "$WORK/film"                      # narrates (cached) and lays out one panel per beat
test -s "$WORK/film/out/storyboard/index.html" && test -s "$WORK/film/out/storyboard/storyboard.pdf"
FPS=8 WORKERS=2 filmwright build "$WORK/film"

python - "$WORK/film" <<'PY'
import json, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
files = [root / p for p in json.loads((root / "out/final/manifest.json").read_text())]
assert any(p.name.endswith("-hd.mp4") for p in files), files
assert any(p.name.endswith("-square.mp4") for p in files), files
assert {"narration", "music", "sfx"} <= {p.stem.rsplit("-", 1)[-1] for p in files if p.suffix == ".wav"}, files
for p in files:
    if p.suffix != ".mp4":
        continue
    tags = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=comment", "-of", "csv=p=0", str(p)],
                          capture_output=True, text=True).stdout.strip()
    assert "synthetic voice" in tags, (p, tags)
print("smoke ok:", ", ".join(p.name for p in files))
PY
