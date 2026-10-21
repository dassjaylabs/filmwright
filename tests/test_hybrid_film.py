import json
import re
from pathlib import Path

import pytest

from filmwright.hybrid.film import EXAMPLE, Film, zoom_expr

REPO = Path(__file__).resolve().parents[1]


def write(tmp_path, segments, **extra):
    import yaml
    spec = tmp_path / "film.yaml"
    spec.write_text(yaml.safe_dump({"file_prefix": "t", "segments": segments, **extra}))
    return spec


def test_bundled_example_matches_the_repo_example():
    assert EXAMPLE.read_text() == (REPO / "examples" / "both" / "film.yaml").read_text()


def test_segments_are_classified(tmp_path):
    f = Film(write(tmp_path, [{"scene": "title", "say": "Hi."}, {"clip": "rec/a.mp4", "say": "Look."}]))
    assert [s["kind"] for s in f.segs] == ["title", "clip"]
    assert f.segs[1]["path"] == tmp_path / "rec" / "a.mp4"


def test_unknown_scene_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        Film(write(tmp_path, [{"scene": "fireworks"}]))


def test_timeline_holds_each_scene_and_tiles_the_film(tmp_path):
    f = Film(write(tmp_path, [{"scene": "title", "say": "Hi."}, {"scene": "steps", "say": "A."}, {"scene": "outro"}]))
    (tmp_path / "beats.json").write_text(json.dumps([{"key": "s01", "text": "Hi.", "dur": 1.0},
                                                     {"key": "s02", "text": "A.", "dur": 1.0},
                                                     {"key": "s03", "text": "", "dur": 0.0}]))
    beats, segs, total = f.timeline()
    assert segs[0]["start"] == 0
    for a, b in zip(segs, segs[1:]):
        assert a["start"] + a["dur"] == pytest.approx(b["start"], abs=1e-3)   # no gaps between segments
    assert segs[1]["dur"] >= 3.6 and segs[2]["dur"] >= 4.2
    assert total == pytest.approx(segs[-1]["start"] + segs[-1]["dur"] + .6)


def test_zoom_expression_eases_in_holds_and_out():
    e = zoom_expr({"at": 1.0, "scale": 1.5, "ramp": .5, "hold": 2.0})

    def at(t):
        py = e.replace("clip(", "_clip(")
        py = re.sub(r"\bt\b", repr(t), py)
        return eval(py, {"_clip": lambda x, a, b: max(a, min(b, x))})
    assert at(0.5) == pytest.approx(1.0)
    assert at(1.25) == pytest.approx(1.25)
    assert at(2.5) == pytest.approx(1.5)
    assert at(5.0) == pytest.approx(1.0)


def test_new_scenes_are_accepted_and_hold_long_enough(tmp_path):
    from filmwright.hybrid.film import MIN_HOLD, SCENES
    for kind in ("headline", "chart", "device", "ui"):
        assert kind in SCENES and MIN_HOLD[kind] >= 2.8
    f = Film(write(tmp_path, [{"scene": k, "say": ""} for k in ("headline", "chart", "device", "ui")]))
    assert [s["kind"] for s in f.segs] == ["headline", "chart", "device", "ui"]


def test_device_screenshots_must_exist(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        Film(write(tmp_path, [{"scene": "device", "image": "missing.png"}]))
    (tmp_path / "shot.png").write_bytes(b"png")
    seg = Film(write(tmp_path, [{"scene": "device", "image": "shot.png"}])).segs[0]
    assert seg["image"].startswith("file://") and seg["image"].endswith("shot.png")


def test_new_scenes_render(tmp_path):
    pytest.importorskip("playwright")
    from filmwright.explainer import render as R
    from filmwright.hybrid.film import TEMPLATE
    segs = [{"kind": "headline", "start": 0, "dur": 3, "text": "Plan *less*.\\nDo more."},
            {"kind": "chart", "start": 3, "dur": 4, "data": [{"label": "A", "value": 3}, {"label": "B", "value": 7}], "note": "+4"},
            {"kind": "chart", "start": 7, "dur": 4, "type": "line", "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
            {"kind": "device", "start": 11, "dur": 4},
            {"kind": "ui", "start": 15, "dur": 5, "steps": [{"click": "input"}, {"type": "Hi"}, {"click": "button"}, {"check": 0}, {"toast": "Done"}]}]
    try:
        total, sfx = R.page_info(TEMPLATE, {"FILM": {"segments": segs}})
    except Exception as e:                                   # no browser installed on this machine
        pytest.skip(f"no headless browser: {e}")
    assert total == pytest.approx(20.6)
    assert {n for _, n in sfx} >= {"click", "pop", "chime", "tick"}
