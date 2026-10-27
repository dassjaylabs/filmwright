"""Camera paths on hybrid clips: `cam` keyframes, the `pan` shorthand, the window frame and the hold scale."""
import json

import pytest
import yaml

from filmwright.hybrid.film import CAM_HOLD, FRAMES, Film, cam_rows, camera_filter, pan_rows


def write(tmp_path, segments, **extra):
    spec = tmp_path / "film.yaml"
    spec.write_text(yaml.safe_dump({"file_prefix": "t", "segments": segments, **extra}))
    return spec


def test_cam_rows_carry_missing_values_forward():
    rows = cam_rows([[0, 1], [0.5, 2.5, 0.22, 0.17], [1.4], [2.3, None, 0.85]])
    assert rows == [[0.0, 1.0, 0.5, 0.5], [0.5, 2.5, 0.22, 0.17], [1.4, 2.5, 0.22, 0.17], [2.3, 2.5, 0.85, 0.17]]


def test_cam_rows_accept_dicts():
    assert cam_rows([{"t": 0, "z": 1}, {"t": 1, "z": 2, "x": 0.3, "y": 0.4}]) == [[0.0, 1.0, 0.5, 0.5], [1.0, 2.0, 0.3, 0.4]]


def test_cam_rows_refuse_out_of_order_times_and_zoom_below_one():
    with pytest.raises(SystemExit):
        cam_rows([[0, 1], [2, 2], [1, 2]])
    with pytest.raises(SystemExit):
        cam_rows([[0, 0.8]])
    with pytest.raises(SystemExit):
        cam_rows([])


def test_pan_holds_every_stop_for_at_least_a_second():
    rows = pan_rows({"zoom": 2.5, "y": 0.2, "stops": [0.22, 0.85, [0.5, 0.6]], "at": 0.4})
    assert rows[0] == [0.0, 1.0, 0.22, 0.2]                 # starts wide, aimed at the first stop
    assert rows[1][1:] == [2.5, 0.22, 0.2]                  # pushed in
    holds = [(b[0] - a[0]) for a, b in zip(rows, rows[1:]) if a[1:] == b[1:]]
    assert holds and all(h >= CAM_HOLD - 1e-6 for h in holds)   # a stop never lasts less than CAM_HOLD
    assert rows[-1][1:] == [2.5, 0.5, 0.6]                  # stays in on the last stop
    xs = [r[2] for r in rows]
    assert xs.index(0.85) > xs.index(0.22)                  # stops are visited in order


def test_pan_can_start_pushed_in_and_ease_out():
    rows = pan_rows({"zoom": 2.6, "stops": [0.4], "at": 0, "out": True})
    assert rows[0][1] == 2.6                                 # no wide shot at the start
    assert rows[-1][1] == 1.0                                # back to wide at the end


def test_a_pan_sets_the_segments_minimum_length(tmp_path):
    f = Film(write(tmp_path, [{"clip": "a.mp4", "pan": {"zoom": 2.5, "stops": [0.2, 0.8]}, "say": "x"}]))
    seg = f.segs[0]
    assert "cam" in seg and "pan" not in seg
    assert seg["seconds"] == pytest.approx(seg["cam"][-1][0])


def test_only_one_camera_per_clip(tmp_path):
    with pytest.raises(SystemExit):
        Film(write(tmp_path, [{"clip": "a.mp4", "zoom": {"scale": 1.3}, "pan": {"stops": [0.5]}}]))


def test_camera_filter_reads_from_the_source_when_the_aspect_matches():
    rows = [[0.0, 1.0, 0.5, 0.5], [1.0, 2.0, 0.25, 0.25]]
    direct = camera_filter(rows, 3200, 1800, (4320, 2430), 60)
    assert direct.startswith("zoompan=") and "s=3200x1800" in direct
    fitted = camera_filter(rows, 3200, 1800, (1000, 1000), 60)
    assert fitted.startswith("scale=3200:1800") and "zoompan=" in fitted


def test_frame_presets_and_custom_frames(tmp_path):
    assert Film(write(tmp_path, [{"scene": "title"}])).frame == FRAMES["default"]
    assert Film(write(tmp_path, [{"scene": "title"}], frame="wide")).frame == FRAMES["wide"]
    assert Film(write(tmp_path, [{"scene": "title"}], frame={"x": 100, "y": 100, "w": 1000, "h": 562})).frame == {"x": 100, "y": 100, "w": 1000, "h": 562}
    with pytest.raises(SystemExit):
        Film(write(tmp_path, [{"scene": "title"}], frame="huge"))
    with pytest.raises(SystemExit):
        Film(write(tmp_path, [{"scene": "title"}], frame={"x": 0, "y": 0, "w": 2000, "h": 1000}))


def test_holds_scale_shortens_the_minimum_time_on_screen(tmp_path):
    def total_for(holds):
        f = Film(write(tmp_path, [{"scene": "title", "say": "Hi."}, {"scene": "steps", "say": "A."}, {"scene": "outro"}], holds=holds))
        (tmp_path / "beats.json").write_text(json.dumps([{"key": "s01", "text": "Hi.", "dur": 0.5},
                                                         {"key": "s02", "text": "A.", "dur": 0.5},
                                                         {"key": "s03", "text": "", "dur": 0.0}]))
        return f.timeline()[2]
    assert total_for(0.75) < total_for(1.0)
    with pytest.raises(SystemExit):
        Film(write(tmp_path, [{"scene": "title"}], holds=0.1))
