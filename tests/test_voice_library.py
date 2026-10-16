import shutil

import pytest

from filmwright import config as C
from filmwright.core.voice import library as L
from filmwright.core.voice import make_voice
from filmwright.core.voice.qwen import sha256


def test_every_bundled_voice_matches_its_checksum():
    lib = L.voices()
    assert len(lib) >= 5
    for name, entry in lib.items():
        clip, text, got = L.reference(name)
        assert clip.parent == L.LIBRARY_DIR and sha256(clip) == entry["sha256"] and text
        assert entry["description"] and entry["label"].lower().startswith(name)


@pytest.mark.parametrize("name", ["", "nobody", "../nora", "/tmp/nora", "Nora", None])
def test_only_names_from_the_library_are_accepted(name):
    with pytest.raises(L.LibraryError):
        L.reference(name)


def test_a_modified_clip_is_refused(tmp_path, monkeypatch):
    lib = tmp_path / "voices"
    shutil.copytree(L.LIBRARY_DIR, lib)
    clip = lib / "nora.wav"
    data = bytearray(clip.read_bytes())
    mid = len(data) // 2
    data[mid:mid + 200] = bytes(255 - b for b in data[mid:mid + 200])     # same length, different audio
    clip.write_bytes(bytes(data))
    monkeypatch.setattr(L, "LIBRARY_DIR", lib)
    monkeypatch.setattr(L, "MANIFEST", lib / "library.json")
    with pytest.raises(L.LibraryError, match="modified"):
        L.reference("nora")


def test_a_user_recording_cant_pose_as_a_library_voice(tmp_path, monkeypatch):
    """Dropping a recording into a copy of the library (with a matching manifest entry) still isn't the bundled
    library: make_voice only ever reads the package's own folder."""
    rogue = tmp_path / "rogue.wav"
    shutil.copyfile(L.LIBRARY_DIR / "nora.wav", rogue)
    with pytest.raises(L.LibraryError):
        make_voice({"type": "library", "name": str(rogue)}, root=tmp_path)
    with pytest.raises(L.LibraryError):
        make_voice({"type": "library", "name": "rogue"}, root=tmp_path)


def test_config_checks_the_name(tmp_path):
    import yaml
    p = tmp_path / "reel.yaml"
    p.write_text(yaml.safe_dump({"mode": "explainer", "voice": {"type": "library", "name": "nobody"}}))
    with pytest.raises(C.ConfigError, match="voice.name"):
        C.load(p)
    p.write_text(yaml.safe_dump({"mode": "explainer", "voice": {"type": "library", "name": "olivia"}}))
    assert C.load(p)["voice"]["name"] == "olivia"
