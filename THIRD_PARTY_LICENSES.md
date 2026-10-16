# Third-party components

filmwright's own code is MIT-licensed (see [LICENSE](LICENSE)). It bundles a few files and installs or runs the
components below. Everything it installs is open source, with the one noted exception (Chrome for Testing, used only
as a fallback where no open-source Chromium build exists). Nothing is uploaded: the browser, the voices, the
read-back check and the music all run on your machine.

## Bundled in this repository

| Component | Where | License |
|---|---|---|
| [IBM Plex Sans](https://github.com/IBM/plex) | `src/filmwright/assets/fonts/` | SIL Open Font License 1.1 (`OFL.txt`) |
| [Space Grotesk](https://github.com/floriankarsten/space-grotesk) | `src/filmwright/assets/fonts/` (when present) | SIL Open Font License 1.1 |
| [Caveat](https://github.com/googlefonts/caveat) | `src/filmwright/assets/fonts/` (when present) | SIL Open Font License 1.1 |
| [rough.js](https://github.com/rough-stuff/rough) | explainer templates | MIT |

The animation engine (`assets/motion.js`) is part of filmwright and MIT-licensed. **GSAP is not used.**
Music and sound effects are synthesised by filmwright's own code (`core/music`, `core/sfx.py`): no samples, nothing
to license. The talking-head characters are drawn in code by filmwright.

## Python packages

| Component | Used for | License |
|---|---|---|
| [Playwright for Python](https://playwright.dev/python/) | drives the browser for recordings and frame rendering | Apache-2.0 |
| [Pillow](https://python-pillow.org) | cards, labels, captions | MIT-CMU (HPND) |
| [PyYAML](https://pyyaml.org) | configuration | MIT |
| [NumPy](https://numpy.org) | music and sound synthesis, audio checks | BSD-3-Clause |
| [MLX](https://github.com/ml-explore/mlx) (optional) | runs the voice models on Apple Silicon | MIT |
| [mlx-audio](https://github.com/Blaizzy/mlx-audio) (optional) | Qwen3-TTS and Whisper on MLX | MIT |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) (via mlx-audio) | downloads models once | Apache-2.0 |
| [transformers](https://github.com/huggingface/transformers) (via mlx-audio) | tokenizers | Apache-2.0 |

## Models (optional, downloaded on request)

| Model | Used for | License |
|---|---|---|
| [Qwen3-TTS 1.7B](https://huggingface.co/Qwen) CustomVoice / VoiceDesign / Base (MLX conversions by mlx-community) | preset, library, described and cloned voices; the bundled library clips (`assets/voices/`) were generated with VoiceDesign | Apache-2.0 |
| [Whisper large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) (MLX conversion) | reads each sentence back; transcribes clone samples | MIT |

## Programs installed by `filmwright setup`

| Component | Used for | License |
|---|---|---|
| [Chromium](https://www.chromium.org) (project snapshot; Debian's `chromium` on Linux ARM) | recording demos, rendering animated scenes | BSD-3-Clause, plus bundled open-source libraries |
| Chrome for Testing (fallback only) | the browser where no open-source Chromium build exists | Chromium under Google's terms; reported as `FALLBACK` |
| [ffmpeg](https://ffmpeg.org) with x264 | recording, cutting, mixing, encoding | LGPL-2.1+ / GPL-2.0+ depending on the build (your videos are not covered by it) |
| [espeak-ng](https://github.com/espeak-ng/espeak-ng) | the system voice | GPL-3.0-or-later (run as a separate program) |
| [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) | the talking head's mouth shapes | MIT (its output belongs to you) |

## Fonts loaded at render time

None: the templates load only bundled fonts, so rendering works offline and needs no third-party requests.

Your operating system, Python itself, Homebrew/apt, and any AI assistant you use to write configuration are not
part of filmwright.
