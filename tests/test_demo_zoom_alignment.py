"""Click zooms land on what was clicked: a target below the fold is logged (and zoomed on) where it is when it's
clicked, not where it was before the scroll, at pixel density 1 and 2; and the recording shows exactly the viewport.

The window-size half is covered by the unit tests: Playwright's bundled Chromium (what CI runs) never captured the
wrong size, and the open-source build only did before the first navigation."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from filmwright.demo.effects import auto_focus_specs, plan_camera, remap
from filmwright.demo.recorder import Recorder, launch_args, scale_for


def test_launch_args_size_the_window_to_the_viewport():
    args = launch_args(3, {"width": 1440, "height": 810})
    assert "--force-device-scale-factor=3" in args and "--window-size=1440,810" in args
    assert not any(a.startswith("--window-size") for a in launch_args(2))


def _frame(rec: Recorder, w: int, h: int, ts: float) -> None:
    rec._on_frame({"sessionId": 1, "data": base64.b64encode(b"jpeg").decode(),
                   "metadata": {"deviceWidth": w, "deviceHeight": h, "timestamp": ts}})


def test_recorder_flags_frames_that_are_not_the_viewport(tmp_path):
    class NoCdp:
        def send(self, *a, **k):
            return {}

    rec = Recorder(None, None, tmp_path / "clip.mp4", {"width": 1440, "height": 810}, 3)
    rec.cdp = NoCdp()
    try:
        _frame(rec, 1440, 810, 1.0)
        assert rec.mismatched() == {}
        _frame(rec, 1440, 723, 1.1)        # what a headless window without --window-size captured
        _frame(rec, 1440, 723, 1.2)
        assert rec.mismatched() == {(1440, 723): 2}
    finally:
        shutil.rmtree(rec.dir, ignore_errors=True)


def test_ready_is_the_first_frame_that_shows_the_scroll(tmp_path):
    class NoCdp:
        def send(self, *a, **k):
            return {}

    rec = Recorder(None, None, tmp_path / "clip.mp4", {"width": 640, "height": 360}, 2)
    rec.cdp = NoCdp()

    class SlowPage:                         # the screencast delivers the scrolled frame a few waits later
        waits = 0

        def wait_for_timeout(self, ms):
            self.waits += 1
            if self.waits == 3:
                _frame(rec, 640, 360, 105.08)
                _frame(rec, 640, 360, 105.11)

    try:
        _frame(rec, 640, 360, 104.9)          # before the scroll
        assert rec.frame_after(SlowPage(), since=105.0) == pytest.approx(105.08)
        rec.stopped = True                     # as stop() leaves it: a frame still in flight is ignored
        _frame(rec, 640, 360, 106.0)
        assert len(rec.frames) == 3
    finally:
        shutil.rmtree(rec.dir, ignore_errors=True)


def test_zoom_waits_for_the_page_to_scroll_to_the_target():
    meta = {"viewport": {"width": 1440, "height": 810}, "events": [
        {"step": 2, "kind": "click", "t": 6.0, "end": 6.4, "box": [300, 220, 200, 60], "ready": 5.6}]}
    at = auto_focus_specs({}, meta, log=lambda *_: None)[0]["at"]
    assert at == pytest.approx(5.85)                 # not 6.0 - 0.9: that would push in over the unscrolled page
    meta["events"][0]["ready"] = 3.0                  # scrolled long before: the usual lead applies
    assert auto_focus_specs({}, meta, log=lambda *_: None)[0]["at"] == pytest.approx(5.1)


def test_cuts_shift_the_ready_time_too():
    meta = {"events": [{"kind": "click", "t": 10.0, "end": 10.5, "ready": 9.0}]}
    assert remap(meta, [(2.0, 5.0)])["events"][0]["ready"] == pytest.approx(6.0)


# ---------------------------------------------------------------------------------------------------------------
# End to end: a red button below the fold, clicked at DPR 1 and 2, in a real browser.

PAGE = """<!doctype html><html><body style="margin:0;background:#fff">
<style>@keyframes spin {{ to {{ transform: rotate(1turn) }} }}</style>
<div style="position:fixed;top:4px;left:4px;width:8px;height:8px;background:#999;animation:spin 1s linear infinite"></div>
<div style="height:{below}px"></div>
<button id=go style="display:block;margin-left:{left}px;width:200px;height:80px;background:#e00000;border:0" aria-label="Go"></button>
<div style="height:1500px"></div></body></html>"""


def _pixel(video: Path, t: float, x: float, y: float) -> tuple[int, int, int]:
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"format=rgb24,crop=1:1:{int(x)}:{int(y)}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                       capture_output=True, check=True)
    return tuple(p.stdout[:3])


def _red(px: tuple[int, ...]) -> bool:
    return len(px) == 3 and px[0] > 170 and px[1] < 90 and px[2] < 90


@pytest.fixture(scope="module")
def browser_ok():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("needs ffmpeg")
    pytest.importorskip("playwright")
    from playwright.sync_api import Error, sync_playwright

    from filmwright.demo.recorder import launch_kwargs
    try:
        with sync_playwright() as p:
            p.chromium.launch(**launch_kwargs(headless=True)).close()
    except Error as e:
        pytest.skip(f"no Chromium: {str(e).splitlines()[0]}")


@pytest.mark.parametrize("viewport", [{"width": 1280, "height": 720}, {"width": 640, "height": 360}],
                         ids=["dpr1", "dpr2"])
def test_click_zoom_lands_on_the_clicked_target(browser_ok, viewport, tmp_path, monkeypatch):
    from filmwright.demo import run_scenarios

    html = PAGE.format(below=viewport["height"] + 400, left=viewport["width"] // 3).encode()

    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        spec = {"name": "zoom alignment", "base_url": f"http://127.0.0.1:{server.server_port}/", "viewport": viewport,
                "recording": {"resolution": "720p", "cursor": False, "ripple": False, "pace": 0.3},
                "scenarios": [{"id": "Z1", "title": "click below the fold", "hold": 1.0,
                               "steps": [{"goto": "/"}, {"pause": 3}, {"click": {"css": "#go"}}, {"pause": 1}]}]}
        (tmp_path / "scenarios.yaml").write_text(json.dumps(spec))
        monkeypatch.setattr(sys, "argv", ["run_scenarios", str(tmp_path / "scenarios.yaml")])
        assert run_scenarios.main() == 0
    finally:
        server.shutdown()

    scale = scale_for("720p", viewport["width"])
    assert scale == (1 if viewport["width"] == 1280 else 2)
    meta = json.loads((tmp_path / "videos" / "Z1.events.json").read_text())
    video = tmp_path / "videos" / "Z1.mp4"
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    assert probe == f"{viewport['width'] * scale},{viewport['height'] * scale}"
    assert "captured" not in meta, f"the browser captured {meta.get('captured')}, not the viewport"

    click = next(e for e in meta["events"] if e["kind"] == "click")
    x, y, w, h = click["box"]
    assert 0 <= y and y + h <= viewport["height"], "box was logged before the button scrolled into view"
    assert click.get("ready") is not None and click["ready"] < click["t"]

    cx, cy = (x + w / 2) * scale, (y + h / 2) * scale            # the box centre in frame px, as effects maps it
    assert _red(_pixel(video, click["t"], cx, cy)), "the frame at the click doesn't show the button at its logged box"

    camera = plan_camera({}, meta, tuple(meta["frame"]), log=lambda *_: None)
    i = next(k for k, kf in enumerate(camera) if kf[1] > 1.0)
    zoom_start, (_, _, zx, zy) = camera[i - 1][0], camera[i]
    assert (zx, zy) == pytest.approx((cx, cy))
    assert zoom_start >= click["ready"] - 0.01
    assert _red(_pixel(video, zoom_start + 0.05, zx, zy)), "the zoom starts before the page shows the button there"
