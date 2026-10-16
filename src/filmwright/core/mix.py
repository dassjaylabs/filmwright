"""Mix narration, music and sound effects into one loudness-normalised track.

    from filmwright.core.mix import mix
    mix("vo.wav", "mix.wav", music_wav="music.wav", sfx_wav="sfx.wav", music_db_under=-20)

- The narration is the reference. Music is levelled to `music_db_under` dB relative to the narration's loudness
  (filmwright uses -20 for a score and -26 for an ambient bed, so the voice always leads), then ducked a little
  further whenever someone speaks.
- Sound effects sit `sfx_db` dB relative to their own level (they are already made quiet by sfx_track()).
- The result is normalised to `target_lufs` (default -16 LUFS, a common level for web video) with a true-peak
  ceiling, 48 kHz stereo.
- With no narration (a silent loop with music only) the music alone is normalised.
- With `stems_dir`, each part is also written there as it sits in the mix (level, ducking and the final
  normalisation gain applied): narration.wav, music.wav, sfx.wav, as 32-bit float WAV. All start at 0 and run the
  mix's full length, so laid side by side in an editor they add up to the mix.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np

STEM_NAMES = ("narration", "music", "sfx")      # the parts `stems_dir` writes, in this order


def _ff(*args: str) -> None:
    p = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-600:]}")


def lufs(path: Path | str) -> float:
    """Integrated loudness of a file's first audio stream (EBU R128), in LUFS. -70.0 for silence."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=framelog=quiet",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", err)
    if not m or m[-1] == "-inf":
        return -70.0
    return float(m[-1])


def mix(narration_wav: Path | str | None, out_wav: Path | str, music_wav: Path | str | None = None,
        sfx_wav: Path | str | None = None, *, music_db_under: float = -20.0, duck: bool = True,
        sfx_db: float = -3.0, narration_delay: float = 0.0, seconds: float | None = None,
        target_lufs: float = -16.0, true_peak: float = -1.5, stems_dir: Path | str | None = None) -> Path:
    """Write the final mix to `out_wav` and return its path."""
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs: list[str] = []
    graph: list[str] = []
    labels: list[str] = []
    trim = f",atrim=0:{seconds:.3f}" if seconds else ""
    pad = f",apad=whole_dur={seconds:.3f}" if seconds else ""
    idx = 0
    voice_level = None
    if narration_wav:
        voice_level = lufs(narration_wav)
        inputs += ["-i", str(narration_wav)]
        ms = int(round(narration_delay * 1000))
        delay = f",adelay={ms}|{ms}" if ms else ""
        graph.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo{delay}{pad}{trim},asplit=2[vk][v]")
        labels.append("[v]")
        idx += 1
    if music_wav:
        inputs += ["-i", str(music_wav)]
        gain = 0.0
        if voice_level is not None and voice_level > -70:
            gain = (voice_level + music_db_under) - lufs(music_wav)
        graph.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB{pad}{trim}[m0]")
        if narration_wav and duck:
            graph.append("[m0][vk]sidechaincompress=threshold=0.035:ratio=3.5:attack=15:release=300[m]")
        else:
            graph.append("[m0]anull[m]")
            if narration_wav:
                graph.append("[vk]anullsink")
        labels.append("[m]")
        idx += 1
    elif narration_wav:
        graph.append("[vk]anullsink")
    if sfx_wav:
        inputs += ["-i", str(sfx_wav)]
        graph.append(f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={sfx_db:.1f}dB{pad}{trim}[s]")
        labels.append("[s]")
        idx += 1
    if not labels:
        raise ValueError("mix() needs at least narration or music")
    names = dict(zip(("[v]", "[m]", "[s]"), STEM_NAMES))
    stem_maps: list[str] = []
    stem_raw: list[tuple[str, Path]] = []
    if stems_dir:
        sd = Path(stems_dir)
        sd.mkdir(parents=True, exist_ok=True)
        for name in STEM_NAMES:                       # a part this mix doesn't have must not survive from an earlier one
            (sd / f"{name}.wav").unlink(missing_ok=True)
        for k, lab in enumerate(labels):
            name = names[lab]
            graph.append(f"{lab}asplit=2[mx{k}][st{k}]")
            raw = sd / f"{name}.raw.wav"
            stem_maps += ["-map", f"[st{k}]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_f32le", str(raw)]
            stem_raw.append((name, raw))
        labels = [f"[mx{k}]" for k in range(len(labels))]
    graph.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest[out]")
    pre = out.with_name(out.stem + ".premix.wav")
    try:
        _ff(*inputs, "-filter_complex", ";".join(graph), "-map", "[out]", "-ar", "48000", "-ac", "2",
            "-c:a", "pcm_f32le", str(pre), *stem_maps)
        normalize(pre, out, target_lufs, true_peak)
        if stem_raw:
            _write_stems(stem_raw, pre, out)
    finally:
        pre.unlink(missing_ok=True)
        for _, raw in stem_raw:
            raw.unlink(missing_ok=True)
    return out


def _pcm(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", "48000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, 2)


def _gain_curve(pre: np.ndarray, post: np.ndarray, win: int = 480) -> np.ndarray:
    """The gain normalize() applied, sample by sample. It is one constant when loudnorm could work linearly, and a
    slow curve (plus the limiter on peaks) when it had to ride the level; measured over 10 ms windows."""
    n = min(len(pre), len(post))
    k = n // win
    if k == 0:
        return np.ones(len(post), "f4")
    a = np.sqrt(np.mean(pre[:k * win].reshape(k, win * 2) ** 2, axis=1))
    b = np.sqrt(np.mean(post[:k * win].reshape(k, win * 2) ** 2, axis=1))
    ok = a > 1e-4
    if not ok.any():
        return np.ones(len(post), "f4")
    centres = (np.arange(k) + 0.5) * win
    return np.interp(np.arange(len(post)), centres[ok], (b[ok] / a[ok])).astype("f4")


def _write_stems(stems: list[tuple[str, Path]], pre: Path, post: Path) -> None:
    """Each stem with the same gain the final normalisation gave the mix, at the mix's length, as 32-bit float
    48 kHz stereo WAV (float, so a narration peak that the mix's limiter tamed isn't clipped in its stem)."""
    mixed = _pcm(post)
    gain = _gain_curve(_pcm(pre), mixed)[:, None]
    for name, raw in stems:
        x = _pcm(raw)[:len(mixed)]
        x = np.pad(x, ((0, len(mixed) - len(x)), (0, 0))) * gain
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ar", "48000", "-ac", "2", "-i", "-",
                        "-c:a", "pcm_f32le", "-fflags", "+bitexact", "-flags:a", "+bitexact",
                        str(raw.with_name(name + ".wav"))], input=x.astype("<f4").tobytes(), check=True)


def normalize(src: Path | str, dst: Path | str, target_lufs: float = -16.0, true_peak: float = -1.5) -> Path:
    """Two-pass EBU R128 normalisation: measure first, then apply one linear gain where possible."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                          f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    if m:
        st = json.loads(m.group(0))
        if st.get("input_i") not in (None, "-inf"):
            af = (f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11:measured_I={st['input_i']}:measured_TP={st['input_tp']}"
                  f":measured_LRA={st['input_lra']}:measured_thresh={st['input_thresh']}:offset={st['target_offset']}:linear=true")
        else:
            af = "anull"
    else:
        af = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
    _ff("-i", str(src), "-af", af, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        "-fflags", "+bitexact", "-flags:a", "+bitexact", str(dst))
    return Path(dst)
