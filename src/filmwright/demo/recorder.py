"""High-quality page recorder: Chrome screencast frames → constant-frame-rate H.264.

Why not Playwright's own recorder? It encodes VP8 at a fixed ~1 Mbit/s and at 1× pixel density,
which smears UI text. This one asks Chrome for JPEG frames at the forced device scale factor (the
browser must be launched with `--force-device-scale-factor=N`). At a 1440×810 viewport and N=3 that
is 4320×2430 at up to 60 fps. Each frame is held until the next one arrives, which keeps the
timing real-time, and the result is encoded at CRF 16. Event timestamps from the runner use the
same clock (`time.time()`), so `t0` maps them onto the video.

The browser window is launched at the viewport's size (`launch_args`). Without that, some headless Chromium
builds (the open-source snapshot `filmwright setup` installs among them) capture the window's own content area
instead of the emulated viewport until the page first navigates: 87 CSS px short at 1440×810, 500 px wide for a
430 px phone viewport. The encoder stretches such a frame to the expected size, which would put every zoom and
callout off its target. Each frame's metadata says what was captured; the recorder checks it and warns when it
isn't the viewport.

Resolutions are named by their output size; `scale_for()` picks the device scale factor that renders
at least that many pixels, so the final film is downscaled (sharp), never upscaled.
"""

from __future__ import annotations

import base64
import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from filmwright.paths import FONTS, cache_dir

RESOLUTIONS = {"4k": (3840, 2160), "1440p": (2560, 1440), "1080p": (1920, 1080), "720p": (1280, 720)}
CHROME_ARGS = ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
               "--disable-background-timer-throttling"]


CACHE = cache_dir()


def chromium_path() -> str | None:
    """The open-source Chromium that `filmwright setup` installed (Chromium project snapshot, or the distro's
    package on Linux ARM), or $FILMWRIGHT_CHROMIUM. None means: fall back to Playwright's own download, which is
    Google's "Chrome for Testing" build, so it isn't open source."""
    if os.environ.get("FILMWRIGHT_CHROMIUM"):
        return os.environ["FILMWRIGHT_CHROMIUM"]
    base = CACHE / "chromium" / "current"
    candidates = [base / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium",
                  base / "chrome-linux" / "chrome", Path("/usr/bin/chromium")]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def launch_kwargs(**extra: Any) -> dict[str, Any]:
    exe = chromium_path()
    if exe is None and not os.environ.get("FILMWRIGHT_QUIET_BROWSER"):
        os.environ["FILMWRIGHT_QUIET_BROWSER"] = "1"
        print("note: open-source Chromium not found, using Playwright's Chrome for Testing build "
              "(not open source). Run `filmwright setup` to install Chromium.", flush=True)
    return {**({"executable_path": exe} if exe else {}), **extra}


def scale_for(resolution: str, viewport_width: int) -> int:
    """Device scale factor so the capture is at least as wide as the output (1–4)."""
    out_w = RESOLUTIONS.get(str(resolution).lower(), RESOLUTIONS["4k"])[0]
    return max(1, min(4, math.ceil(out_w / max(1, viewport_width))))


def launch_args(scale: int, viewport: dict[str, int] | None = None) -> list[str]:
    """Chromium flags for a recording browser. Pass the viewport: the window is then sized to it, so the screencast
    captures exactly the viewport (see the module docstring)."""
    size = [f"--window-size={int(viewport['width'])},{int(viewport['height'])}"] if viewport else []
    return [f"--force-device-scale-factor={scale}", *size, *CHROME_ARGS]


class Recorder:
    def __init__(self, context: Any, page: Any, out_mp4: Path, viewport: dict[str, int], scale: int,
                 fps: int = 30, quality: int = 92):
        self.context, self.page, self.out = context, page, Path(out_mp4)
        self.viewport = (int(viewport["width"]), int(viewport["height"]))
        self.size = (self.viewport[0] * scale, self.viewport[1] * scale)
        self.captured: dict[tuple[int, int], int] = {}   # CSS size each frame says it shows -> number of frames
        self.fps, self.quality = fps, quality
        self.dir = Path(tempfile.mkdtemp(prefix="filmwright-frames-"))
        self.frames: list[tuple[float, Path]] = []
        self.cdp: Any = None
        self.t0: float | None = None          # timestamp of the first frame (same clock as time.time())
        self.started_at = 0.0

    def _on_frame(self, params: dict[str, Any]) -> None:
        try:
            self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass
        meta = params.get("metadata") or {}
        ts = float(meta.get("timestamp") or time.time())
        if meta.get("deviceWidth") and meta.get("deviceHeight"):
            dims = (round(float(meta["deviceWidth"])), round(float(meta["deviceHeight"])))
            self.captured[dims] = self.captured.get(dims, 0) + 1
        if self.t0 is None:
            self.t0 = ts
        path = self.dir / f"f{len(self.frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((ts, path))

    def start(self) -> None:
        self.started_at = time.time()
        self.cdp = self.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self._cast()

    def _cast(self) -> None:
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": self.quality,
                                               "maxWidth": self.size[0], "maxHeight": self.size[1],
                                               "everyNthFrame": 1})

    def kick(self) -> None:
        """Re-issue the screencast, e.g. after a navigation swapped the renderer. Harmless otherwise."""
        try:
            self._cast()
        except Exception:
            pass

    def rel(self, wall: float) -> float:
        """A time.time() value → seconds into the recording."""
        return round(wall - (self.t0 if self.t0 is not None else self.started_at), 3)

    def mismatched(self) -> dict[tuple[int, int], int]:
        """Frames whose captured area is not the viewport, by size. A zoom maps CSS px to frame px by the viewport, so
        on these frames it would miss its target."""
        return {d: n for d, n in self.captured.items()
                if abs(d[0] - self.viewport[0]) > 1 or abs(d[1] - self.viewport[1]) > 1}

    def stop(self) -> Path | None:
        end = time.time()
        bad = self.mismatched()
        if bad:
            sizes = ", ".join(f"{w}×{h} ({n} frames)" for (w, h), n in sorted(bad.items(), key=lambda kv: -kv[1]))
            print(f"warning: {self.out.name}: the browser captured {sizes}, not the {self.viewport[0]}×{self.viewport[1]} "
                  "viewport, so the picture is stretched and zooms and callouts miss their targets. Launch the browser "
                  "with launch_args(scale, viewport) so its window matches the viewport.", flush=True)
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        try:
            if not self.frames:
                return None
            lines = []
            for i, (ts, path) in enumerate(self.frames):
                nxt = self.frames[i + 1][0] if i + 1 < len(self.frames) else end
                lines.append(f"file '{path}'\nduration {max(1.0 / 120, nxt - ts):.4f}\n")
            lines.append(f"file '{self.frames[-1][1]}'\n")   # concat demuxer: repeat the last frame
            listing = self.dir / "frames.txt"
            listing.write_text("".join(lines))
            w, h = (self.size[0] // 2 * 2, self.size[1] // 2 * 2)
            self.out.parent.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                 "-vf", f"fps={self.fps},scale={w}:{h}:flags=lanczos,format=yuv420p",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart", str(self.out)],
                capture_output=True, text=True)
            if p.returncode:
                raise RuntimeError(f"encoding {self.out.name} failed: {p.stderr[-600:]}")
            return self.out
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)


def with_fonts(html: Path) -> Path:
    """A copy of the scene beside the original, with the bundled IBM Plex Sans (SIL OFL) declared, so
    scenes look the same on every machine without relying on system fonts."""
    faces = "".join(
        f'@font-face{{font-family:"IBM Plex Sans";font-weight:{w};src:url("{(FONTS / f"IBMPlexSans-{n}.ttf").as_uri()}")}}'
        for n, w in (("Regular", 400), ("SemiBold", 600), ("Bold", 700)))
    html = Path(html).resolve()
    text = html.read_text()
    # The copy lives in a temp folder (the original may sit in a read-only install), so a <base> keeps the
    # scene's relative scripts and images resolving next to the original.
    style = f'<base href="{html.parent.as_uri()}/"><style>{faces}</style>'
    text = text.replace("<head>", "<head>" + style, 1) if "<head>" in text else style + text
    out = Path(tempfile.mkdtemp(prefix="filmwright-scene-")) / (html.stem + ".html")
    out.write_text(text)
    return out


def _record_stepped(page: Any, out_mp4: Path, seconds: float, fps: int, size: tuple[int, int]) -> Path:
    """Frame-stepped capture of a scene that defines window.__seek(t) (see templates/brand-scenes/runtime.js).
    The clock is ours: for each frame we set the scene to t = i/fps and take a screenshot, so the take is
    identical on every run and does not depend on how busy the machine is."""
    n = max(1, round(seconds * fps))
    tmp = Path(tempfile.mkdtemp(prefix="filmwright-steps-"))
    try:
        page.wait_for_load_state("load")
        page.evaluate("document.fonts.ready.then(() => true)")
        for i in range(n):
            page.evaluate("t => window.__seek(t)", i / fps)
            page.screenshot(path=str(tmp / f"f{i:06d}.jpg"), type="jpeg", quality=92)
        w, h = size[0] // 2 * 2, size[1] // 2 * 2
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        p = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(fps),
                            "-i", str(tmp / "f%06d.jpg"), "-vf", f"scale={w}:{h}:flags=lanczos,format=yuv420p",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart", str(out_mp4)],
                           capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError(f"encoding {out_mp4.name} failed: {p.stderr[-600:]}")
        return out_mp4
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def record_html(html: Path, out_mp4: Path, seconds: float, resolution: str = "4k",
                viewport: dict[str, int] | None = None, fps: int = 30) -> Path:
    """Record a local HTML animation (an explainer scene) for `seconds`. The page gets ?d=<seconds> so it
    can pace itself to the narration.

    A scene built on runtime.js (it defines window.__seek) is captured frame by frame on a controlled clock:
    exact and independent of CPU load. Older real-time scenes fall back to a live screencast.
    The output is always at least `resolution` wide; vertical scenes pass a portrait viewport."""
    from playwright.sync_api import sync_playwright
    vp = viewport or {"width": 1440, "height": 810}
    out_w = RESOLUTIONS.get(str(resolution).lower(), RESOLUTIONS["4k"])[0]
    if vp["height"] > vp["width"]:                      # portrait: the named width is the short side
        out_w = {3840: 1440, 2560: 1440, 1920: 1080, 1280: 720}.get(out_w, 1080)
    scale = max(1, min(4, math.ceil(out_w / max(1, vp["width"]))))
    out = None
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs(args=launch_args(scale, vp)))
        scene = with_fonts(Path(html))
        try:
            ctx = browser.new_context(viewport=vp)
            page = ctx.new_page()
            page.goto(scene.as_uri() + f"?d={seconds:.2f}&capture=1")
            try:
                page.wait_for_function("window.__ready === true", timeout=2500)
                seekable = True
            except Exception:
                seekable = False
            if seekable:
                size = (vp["width"] * scale, vp["height"] * scale)
                out = _record_stepped(page, Path(out_mp4), seconds, fps, size)
                ctx.close()
            else:                                         # legacy real-time scene
                ctx.close()
                context = browser.new_context(viewport=vp)
                page = context.new_page()
                rec = Recorder(context, page, out_mp4, vp, scale, fps=fps)
                rec.start()
                page.goto(scene.as_uri() + f"?d={seconds:.2f}")
                rec.kick()
                page.wait_for_timeout(seconds * 1000)
                out = rec.stop()
                context.close()
        finally:
            shutil.rmtree(scene.parent, ignore_errors=True)
        browser.close()
    if out is None:
        raise RuntimeError(f"no frames recorded from {html}")
    return out
