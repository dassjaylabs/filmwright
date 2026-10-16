#!/usr/bin/env bash
# filmwright: system dependency check / install.
#
#   setup.sh --check                    report OK / MISSING for every dependency, change nothing
#   setup.sh                            install everything that doesn't need an admin password
#   setup.sh --voice preset|library|described|clone|all
#                                       also the neural voices (Apple Silicon only): mlx-audio into the current
#                                       Python environment, and the models that voice type needs:
#       preset    = built-in speakers           CustomVoice 4.2 GB + Whisper 1.6 GB
#       library   = a ready-made narrator        Base 4.2 GB + Whisper 1.6 GB
#       described = a voice described in words  VoiceDesign 4.2 GB + Base 4.2 GB + Whisper 1.6 GB
#       clone     = a consented voice sample    Base 4.2 GB + Whisper 1.6 GB
#     Combine with --check to see what's cached. Models go to the Hugging Face cache (~/.cache/huggingface).
#
# Environment:
#   PYTHON            the interpreter filmwright runs with (default: python3 on PATH). Python packages are
#                     installed into THIS interpreter's environment; setup.sh never creates a venv.
#   FILMWRIGHT_CACHE  where Chromium and Rhubarb go (default: ${XDG_CACHE_HOME:-~/.cache}/filmwright)
#   FILMWRIGHT_CHROMIUM_REVISION   a Chromium snapshot revision, or "latest"
#
# Two tiers, on purpose:
#   * user-level (installed here, idempotent): ffmpeg, espeak-ng (Homebrew on macOS), Python packages,
#     the Chromium project's open-source Chromium, Rhubarb Lip Sync for the talking head.
#   * system-level (needs a password or an interactive installer: Xcode Command Line Tools, Homebrew itself,
#     `sudo apt-get`): printed as commands for you to run, never run here, because an unattended prompt just
#     hangs. Running as root (e.g. in a container) is the exception: then apt installs run directly.
#
# Exit codes: 0 all good, 2 needs you to run the printed commands, 1 an install failed.
# Works with macOS's bash 3.2 (no associative arrays).

set -uo pipefail

MODE="install"
VOICE=""
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --voice) VOICE="preset" ;;
    --voice=*) VOICE="${arg#--voice=}" ;;
    preset|library|described|clone|all)
      if [[ "${PREV:-}" == "--voice" ]]; then VOICE="$arg"; else echo "unknown option: $arg (did you mean --voice $arg?)" >&2; exit 1; fi ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 1 ;;
  esac
  PREV="$arg"
done
case "$VOICE" in ""|preset|library|described|clone|all) ;; *) echo "--voice takes preset, library, described, clone or all" >&2; exit 1 ;; esac

OS="$(uname -s)"
ARCH="$(uname -m)"
IS_ROOT=0; [[ "$(id -u)" == "0" ]] && IS_ROOT=1
HAVE_APT=0; command -v apt-get >/dev/null 2>&1 && HAVE_APT=1
CACHE="${FILMWRIGHT_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/filmwright}"
PY="${PYTHON:-$(command -v python3 || true)}"

ROWS=()        # "name|status|detail"
TODO=()        # commands the person must run themselves
FAILED=0

row()  { ROWS+=("$1|$2|$3"); }
todo() { TODO+=("$1"); }
have() { command -v "$1" >/dev/null 2>&1; }
say_step() { [[ "$MODE" == "install" ]] && echo "==> $*"; }

brew_bin() {
  if have brew; then command -v brew
  elif [[ -x /opt/homebrew/bin/brew ]]; then echo /opt/homebrew/bin/brew
  elif [[ -x /usr/local/bin/brew ]]; then echo /usr/local/bin/brew
  fi
}

APT_UPDATED=0
apt_install() {   # apt_install <pkg...>; runs directly only as root, else queues a sudo command
  if [[ $IS_ROOT -eq 1 ]]; then
    if [[ $APT_UPDATED -eq 0 ]]; then DEBIAN_FRONTEND=noninteractive apt-get update -qq || return 1; APT_UPDATED=1; fi
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@" >/dev/null || return 1
    return 0
  fi
  todo "sudo apt-get update && sudo apt-get install -y $*"
  return 3
}

brew_install() {
  local b; b="$(brew_bin)"
  [[ -z "$b" ]] && return 3
  "$b" install "$@" >/dev/null 2>&1 || "$b" install "$@" || return 1
}

# --- 1. platform basics -----------------------------------------------------------------------

case "$OS" in
  Darwin)
    if xcode-select -p >/dev/null 2>&1; then row "Xcode Command Line Tools" OK "$(xcode-select -p)"
    else row "Xcode Command Line Tools" MISSING "needed by Homebrew"; todo "xcode-select --install"; fi
    if [[ -n "$(brew_bin)" ]]; then row "Homebrew" OK "$(brew_bin)"
    else
      row "Homebrew" MISSING "installs ffmpeg and espeak-ng"
      todo '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    fi
    ;;
  Linux)
    if [[ $HAVE_APT -eq 1 ]]; then row "apt-get" OK "Debian/Ubuntu"
    else row "package manager" MISSING "only apt is automated; install ffmpeg and espeak-ng yourself"; fi
    ;;
  *) row "platform" MISSING "$OS is not supported: use macOS, Linux or WSL" ;;
esac

for tool in curl unzip; do
  if have "$tool"; then row "$tool" OK "$(command -v "$tool")"
  else
    row "$tool" MISSING ""
    if [[ "$MODE" == "install" && "$OS" == "Linux" && $HAVE_APT -eq 1 ]]; then apt_install "$tool" && ROWS[${#ROWS[@]}-1]="$tool|INSTALLED|apt"; fi
  fi
done

# --- 2. Python ----------------------------------------------------------------------------------

py_ok() { [[ -n "$1" ]] && "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; }
if py_ok "$PY"; then row "Python 3.11+" OK "$PY ($("$PY" -c 'import platform; print(platform.python_version())'))"
else
  row "Python 3.11+" MISSING "${PY:-python3} is missing or too old; set PYTHON=/path/to/python3.11+"
  [[ "$OS" == "Darwin" ]] && todo "brew install python@3.12"
  [[ "$OS" == "Linux" && $IS_ROOT -eq 0 ]] && todo "sudo apt-get install -y python3 python3-venv python3-pip"
  PY=""
fi

pkgs_ok() { [[ -n "$PY" ]] && "$PY" -c 'import playwright, PIL, yaml, numpy' >/dev/null 2>&1; }
if pkgs_ok; then row "Python packages" OK "playwright, pillow, pyyaml, numpy"
elif [[ -z "$PY" ]]; then row "Python packages" MISSING "needs Python 3.11+ first"
elif [[ "$MODE" == "check" ]]; then row "Python packages" MISSING "pip install filmwright (or run setup without --check)"
else
  say_step "installing Python packages into $PY"
  if "$PY" -m pip install -q "playwright>=1.47,<2" "pillow>=10.3" "pyyaml>=6.0" "numpy>=1.26" && pkgs_ok; then
    row "Python packages" INSTALLED "$PY"
  else row "Python packages" FAILED "$PY -m pip install playwright pillow pyyaml numpy"; FAILED=1; fi
fi

# --- 3. ffmpeg ----------------------------------------------------------------------------------

if have ffmpeg && have ffprobe; then row "ffmpeg" OK "$(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
else
  if [[ "$MODE" == "install" ]]; then
    say_step "installing ffmpeg"
    if [[ "$OS" == "Darwin" ]]; then brew_install ffmpeg || FAILED=1
    elif [[ $HAVE_APT -eq 1 ]]; then apt_install ffmpeg || true; fi
  fi
  if have ffmpeg && have ffprobe; then row "ffmpeg" INSTALLED "$(command -v ffmpeg)"
  else row "ffmpeg" MISSING "records, mixes and encodes"; [[ "$OS" == "Darwin" ]] && todo "brew install ffmpeg"; fi
fi

# --- 4. espeak-ng: the system voice, on every platform --------------------------------------------

if have espeak-ng; then row "espeak-ng (system voice)" OK "$(command -v espeak-ng)"
else
  if [[ "$MODE" == "install" ]]; then
    say_step "installing espeak-ng"
    if [[ "$OS" == "Darwin" ]]; then brew_install espeak-ng || true
    elif [[ $HAVE_APT -eq 1 ]]; then apt_install espeak-ng || true; fi
  fi
  if have espeak-ng; then row "espeak-ng (system voice)" INSTALLED "$(command -v espeak-ng)"
  else row "espeak-ng (system voice)" MISSING "fallback narration voice"; [[ "$OS" == "Darwin" ]] && todo "brew install espeak-ng"; fi
fi

# --- 5. Chromium (open source) -------------------------------------------------------------------
# Playwright's own download is Google's "Chrome for Testing" build (Chromium plus Google's terms). filmwright
# runs the Chromium project's open-source snapshot instead, pinned to a revision tested with Playwright 1.5x.
# Linux ARM has no snapshots: Debian's `chromium` package is used there; only where neither exists does it
# fall back to Chrome for Testing, and says so.

CHROME_DIR="$CACHE/chromium"
case "$OS-$ARCH" in
  Darwin-arm64)  SNAP="Mac_Arm";   PIN=1708531; ZIP="chrome-mac.zip" ;;
  Darwin-x86_64) SNAP="Mac";       PIN=1708530; ZIP="chrome-mac.zip" ;;
  Linux-x86_64)  SNAP="Linux_x64"; PIN=1708530; ZIP="chrome-linux.zip" ;;
  *)             SNAP="" ;;
esac
chromium_exe() {
  local c
  if [[ -n "${FILMWRIGHT_CHROMIUM:-}" ]]; then echo "$FILMWRIGHT_CHROMIUM"; return 0; fi
  for c in "$CHROME_DIR/current/chrome-mac/Chromium.app/Contents/MacOS/Chromium" "$CHROME_DIR/current/chrome-linux/chrome" /usr/bin/chromium; do
    [[ -x "$c" ]] && { echo "$c"; return 0; }
  done
  return 1
}
launch_ok() {   # launch_ok [executable]: can Playwright start this browser?
  [[ -n "$PY" ]] && pkgs_ok && "$PY" - "${1:-}" <<'EOF' >/dev/null 2>&1
import sys
from playwright.sync_api import sync_playwright
kw = {"executable_path": sys.argv[1]} if sys.argv[1] else {}
with sync_playwright() as p:
    b = p.chromium.launch(**kw); b.new_page().set_content("<p>ok</p>"); b.close()
EOF
}
chromium_ok() { local exe; exe="$(chromium_exe)" && launch_ok "$exe"; }
is_debian() { [[ -r /etc/os-release ]] && grep -qE '^ID=debian' /etc/os-release; }
chromium_version() { local exe; exe="$(chromium_exe)" && "$exe" --version 2>/dev/null | head -1; }

if [[ -n "$PY" && "$OS" == "Linux" && $IS_ROOT -eq 1 && "$MODE" == "install" ]] && pkgs_ok; then
  "$PY" -m playwright install-deps chromium >/dev/null 2>&1 || true   # system libraries only
fi
if chromium_ok; then row "Chromium (open source)" OK "$(chromium_version)"
elif [[ "$MODE" == "check" ]] && launch_ok ""; then
  if [[ -n "$SNAP" ]]; then row "Chromium (open source)" MISSING "not installed yet (Chrome for Testing works meanwhile); run setup"
  else row "Chromium (open source)" FALLBACK "none for $OS-$ARCH; using Chrome for Testing (not open source)"; fi
elif [[ "$MODE" == "check" ]] || ! pkgs_ok; then row "Chromium (open source)" MISSING "run setup without --check"
else
  if [[ -n "$SNAP" ]]; then
    REV="${FILMWRIGHT_CHROMIUM_REVISION:-$PIN}"
    [[ "$REV" == "latest" ]] && REV="$(curl -fsSL "https://commondatastorage.googleapis.com/chromium-browser-snapshots/$SNAP/LAST_CHANGE")"
    say_step "downloading open-source Chromium r$REV for $SNAP (~180-250 MB)"
    mkdir -p "$CHROME_DIR/$REV"
    if curl -fsSL -o "$CHROME_DIR/$REV/$ZIP" "https://commondatastorage.googleapis.com/chromium-browser-snapshots/$SNAP/$REV/$ZIP" \
       && (cd "$CHROME_DIR/$REV" && unzip -q -o "$ZIP" && rm -f "$ZIP"); then
      ln -sfn "$CHROME_DIR/$REV" "$CHROME_DIR/current"
    fi
  elif [[ $HAVE_APT -eq 1 ]] && is_debian; then   # Debian packages real Chromium; Ubuntu only has a snap stub
    say_step "installing Debian's open-source chromium package"; apt_install chromium || true
  fi
  if chromium_ok; then row "Chromium (open source)" INSTALLED "$(chromium_version)"
  else
    say_step "no open-source Chromium for this platform; falling back to Playwright's Chrome for Testing"
    if [[ "$OS" == "Linux" && $IS_ROOT -eq 1 ]]; then "$PY" -m playwright install --with-deps chromium >/dev/null
    else "$PY" -m playwright install chromium >/dev/null; fi
    row "Chromium (open source)" FALLBACK "none for $OS-$ARCH; using Chrome for Testing (not open source)"
  fi
fi

# --- 6. Rhubarb Lip Sync (talking-head mouth shapes; MIT) -----------------------------------------
# Prebuilt for macOS and Linux x86_64. Elsewhere the talking head falls back to loudness-driven mouth shapes.

RH_DIR="$CACHE/rhubarb"
RH_VER="1.14.0"
case "$OS-$ARCH" in
  Darwin-*)      RH_ZIP="Rhubarb-Lip-Sync-$RH_VER-macOS.zip" ;;
  Linux-x86_64)  RH_ZIP="Rhubarb-Lip-Sync-$RH_VER-Linux.zip" ;;
  *)             RH_ZIP="" ;;
esac
rhubarb_exe() {
  local c
  if [[ -n "${FILMWRIGHT_RHUBARB:-}" ]]; then echo "$FILMWRIGHT_RHUBARB"; return 0; fi
  for c in "$RH_DIR"/*/rhubarb; do [[ -x "$c" ]] && { echo "$c"; return 0; }; done
  have rhubarb && { command -v rhubarb; return 0; }
  return 1
}
rhubarb_ok() { local exe; exe="$(rhubarb_exe)" && "$exe" --version >/dev/null 2>&1; }
if rhubarb_ok; then row "Rhubarb Lip Sync" OK "$(rhubarb_exe)"
elif [[ -z "$RH_ZIP" ]]; then row "Rhubarb Lip Sync" "N/A" "no build for $OS-$ARCH; the talking head uses loudness lip-sync"
elif [[ "$MODE" == "check" ]]; then row "Rhubarb Lip Sync" MISSING "run setup without --check (needed only for talking heads)"
else
  say_step "downloading Rhubarb Lip Sync $RH_VER (~90 MB)"
  mkdir -p "$RH_DIR"
  if curl -fsSL -o "$RH_DIR/$RH_ZIP" "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v$RH_VER/$RH_ZIP" \
     && (cd "$RH_DIR" && unzip -q -o "$RH_ZIP" && rm -f "$RH_ZIP") && rhubarb_ok; then
    row "Rhubarb Lip Sync" INSTALLED "$(rhubarb_exe)"
  else row "Rhubarb Lip Sync" FAILED "download or run; the talking head will use loudness lip-sync"; fi
fi

# --- 7. optional: neural voices (Apple Silicon) ---------------------------------------------------

QBASE="mlx-community/Qwen3-TTS-12Hz-1.7B"
WHISPER_REPO="mlx-community/whisper-large-v3-turbo-asr-fp16"   # the plain -turbo repo lacks the processor
voice_repos() {   # what a voice type needs; Whisper reads every sentence back (and transcribes clone samples)
  case "$1" in
    preset)    echo "$QBASE-CustomVoice-bf16 $WHISPER_REPO" ;;
    described) echo "$QBASE-VoiceDesign-bf16 $QBASE-Base-bf16 $WHISPER_REPO" ;;
    clone|library) echo "$QBASE-Base-bf16 $WHISPER_REPO" ;;
    all)       echo "$QBASE-Base-bf16 $QBASE-VoiceDesign-bf16 $QBASE-CustomVoice-bf16 $WHISPER_REPO" ;;
  esac
}
repo_label() { case "$1" in *whisper*) echo "Whisper (read-back)|1.6 GB" ;; *) r="${1%-bf16}"; echo "Qwen3-TTS ${r##*-}|4.2 GB" ;; esac; }
mlx_ok() { [[ -n "$PY" ]] && "$PY" -c 'import mlx_audio' >/dev/null 2>&1; }
# Ask huggingface_hub for config.json and look for weights beside it (directory sizes lie: HF's cache links blobs).
repo_cached() {
  "$PY" - "$1" <<'EOF' >/dev/null 2>&1
import sys, pathlib
from huggingface_hub import try_to_load_from_cache
cfg = try_to_load_from_cache(sys.argv[1], "config.json")
raise SystemExit(0 if isinstance(cfg, str) and any(pathlib.Path(cfg).parent.rglob("*.safetensors")) else 1)
EOF
}

if [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
  if [[ -z "$VOICE" ]]; then
    if mlx_ok; then row "neural voices (optional)" OK "mlx-audio installed; models: setup --check --voice all"
    else row "neural voices (optional)" OPTIONAL "preset / library / described / cloned voices: setup --voice preset|library|described|clone"; fi
  else
    if mlx_ok; then row "mlx-audio" OK "$("$PY" -c 'import importlib.metadata as m; print(m.version("mlx-audio"))')"
    elif [[ "$MODE" == "check" ]]; then row "mlx-audio" MISSING "run: setup --voice $VOICE"
    elif [[ -z "$PY" ]]; then row "mlx-audio" MISSING "needs Python 3.11+ first"
    else
      say_step "installing mlx-audio into $PY"
      if "$PY" -m pip install -q "mlx-audio>=0.5.7,<0.6"; then row "mlx-audio" INSTALLED "$PY"
      else row "mlx-audio" FAILED "$PY -m pip install 'mlx-audio>=0.5.7,<0.6'"; FAILED=1; fi
    fi
    for repo in $(voice_repos "$VOICE"); do
      IFS='|' read -r label size <<<"$(repo_label "$repo")"
      if mlx_ok && repo_cached "$repo"; then row "$label" OK "cached ($repo)"
      elif [[ "$MODE" == "check" ]] || ! mlx_ok; then row "$label" MISSING "$size download: setup --voice $VOICE"
      else
        say_step "downloading $repo ($size)"
        if "$PY" -c "import sys; from huggingface_hub import snapshot_download as s; s(sys.argv[1])" "$repo" \
           && repo_cached "$repo"; then row "$label" INSTALLED "$repo"
        else row "$label" FAILED "download of $repo"; FAILED=1; fi
      fi
    done
  fi
else
  row "neural voices (optional)" "N/A" "need an Apple Silicon Mac; narration uses the system voice (espeak-ng)"
fi

# --- report -------------------------------------------------------------------------------------

printf '\n%-28s %-10s %s\n' "DEPENDENCY" "STATUS" "DETAIL"
printf '%-28s %-10s %s\n' "----------" "------" "------"
MISSING=0
for r in "${ROWS[@]}"; do
  IFS='|' read -r name status detail <<<"$r"
  printf '%-28s %-10s %s\n' "$name" "$status" "$detail"
  [[ "$status" == "MISSING" || "$status" == "FAILED" ]] && MISSING=1
done

if [[ ${#TODO[@]} -gt 0 ]]; then
  echo
  echo "Run these yourself (they need your password or an interactive installer), then run setup again:"
  for t in "${TODO[@]}"; do echo "  $t"; done
fi

[[ $FAILED -eq 1 ]] && exit 1
[[ $MISSING -eq 1 ]] && exit 2
exit 0
