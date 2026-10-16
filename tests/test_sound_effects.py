import json
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from filmwright import build
from filmwright import config as C
from filmwright.core import sfx


def write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "reel.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def peak(path: Path) -> float:
    with wave.open(str(path)) as w:
        return float(np.abs(np.frombuffer(w.readframes(w.getnframes()), "<i2")).max(initial=0))


def test_default_is_subtle_and_bad_values_are_refused(tmp_path):
    assert C.load(write(tmp_path, {"mode": "explainer"}))["sound_effects"] == "subtle"
    with pytest.raises(C.ConfigError, match="sound_effects"):
        C.load(write(tmp_path, {"mode": "explainer", "sound_effects": "loud"}))


@pytest.mark.parametrize("sounds, plays", [
    ("subtle", {"click", "pop", "tick", "chime"}),
    ("full", {"click", "pop", "tick", "chime", "whoosh", "swish", "riser", "impact"}),
    ("off", set()),
])
def test_which_sounds_play(sounds, plays):
    names = ["click", "pop", "tick", "chime", "whoosh", "swish", "riser", "impact"]
    assert {n for n in names if sfx.allowed(n, sounds)} == plays


def test_subtle_track_has_no_transition_sounds(tmp_path):
    cues = [(0.1, "whoosh"), (0.8, "swish"), (1.4, "riser"), (2.6, "impact")]
    assert peak(sfx.sfx_track(cues, 4.0, tmp_path / "subtle.wav")) == 0
    assert peak(sfx.sfx_track(cues, 4.0, tmp_path / "full.wav", sounds="full")) > 0
    assert peak(sfx.sfx_track([(0.1, "click")], 1.0, tmp_path / "click.wav")) > 0


def test_setting_reaches_the_animated_pipelines(tmp_path):
    cfg = C.load(write(tmp_path, {"mode": "explainer", "sound_effects": "full"}))
    assert json.loads(build._settings(cfg, tmp_path).read_text())["music"]["sound_effects"] == "full"


@pytest.mark.parametrize("setting, own, expected", [
    ("off", True, False),
    ("full", {"level": 0.3}, {"level": 0.3, "sounds": "full"}),
    ("subtle", True, {"sounds": "subtle"}),
])
def test_setting_reaches_demo_films(tmp_path, setting, own, expected):
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"sfx": own, "sections": []}))
    reel = C.load(write(tmp_path, {"mode": "demo", "voice": {"type": "system"}, "sound_effects": setting}))
    assert yaml.safe_load(build._resolve_demo(reel, tmp_path)[0].read_text())["sfx"] == expected


def test_demo_keeps_its_own_sfx_when_the_reel_is_silent_on_it(tmp_path):
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"sfx": False, "sections": []}))
    reel = C.load(write(tmp_path, {"mode": "demo", "voice": {"type": "system"}}))
    assert yaml.safe_load(build._resolve_demo(reel, tmp_path)[0].read_text())["sfx"] is False


def test_no_example_pins_the_old_loud_music_level():
    root = Path(__file__).resolve().parents[1]
    for p in [*root.glob("examples/*/*.json"), *root.glob("examples/*/*.yaml"),
              *root.glob("src/filmwright/templates/*/example/*")]:
        assert "-14" not in p.read_text(), p
