import shutil

import pytest

from filmwright.core.voice import VOICE_TYPES, EspeakVoice, make_voice, mlx_status


def test_voice_types():
    assert VOICE_TYPES == ("preset", "library", "described", "clone", "system")


def test_unknown_type_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_voice({"type": "robot"}, root=tmp_path)


def test_described_needs_a_description(tmp_path):
    with pytest.raises(ValueError, match="description"):
        make_voice({"type": "described"}, root=tmp_path)


def test_clone_needs_a_sample(tmp_path):
    with pytest.raises(ValueError, match="sample"):
        make_voice({"type": "clone"}, root=tmp_path)


@pytest.mark.skipif(not shutil.which("espeak-ng"), reason="espeak-ng not installed")
def test_system_voice_speaks(tmp_path):
    v = make_voice({"type": "system"}, root=tmp_path)
    assert isinstance(v, EspeakVoice) and v.kind == "system"
    secs = v.say("Hello there. This is a short test.", tmp_path / "out.wav")
    assert secs > 0.5


@pytest.mark.skipif(not shutil.which("espeak-ng") or mlx_status() is None, reason="needs espeak-ng and no MLX")
def test_preset_falls_back_to_system_voice(tmp_path):
    notes = []
    v = make_voice({"type": "preset"}, root=tmp_path, log=notes.append)
    assert v.kind == "system"
    assert notes and "system voice" in notes[0]
