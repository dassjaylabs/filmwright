from pathlib import Path

import pytest
import yaml

from filmwright import build, cli, wizard
from filmwright import config as C


def write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "reel.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_defaults_fill_in(tmp_path):
    cfg = C.load(write(tmp_path, {"mode": "explainer"}))
    assert cfg["voice"]["type"] == "preset"
    assert cfg["music"]["mood"] == "upbeat"
    assert cfg["outputs"] == ["4k", "hd"]
    assert cfg["disclosure"] == "metadata"
    assert cfg["explainer"]["format"] == "story"


@pytest.mark.parametrize("bad, message", [
    ({"mode": "movie"}, "mode"),
    ({"music": {"mood": "angry"}}, "music.mood"),
    ({"outputs": ["8k"]}, "outputs"),
    ({"outputs": ["stems"]}, "stems come with a video"),
    ({"voice": {"type": "described"}}, "voice.description"),
    ({"voice": {"type": "clone"}}, "voice.sample"),
    ({"talking_head": {"enabled": True, "character": "nobody"}}, "talking_head.character"),
    ({"disclosure": "sometimes"}, "disclosure"),
    ({"surprise": 1}, "unknown key"),
])
def test_validation_errors(tmp_path, bad, message):
    with pytest.raises(C.ConfigError, match=message):
        C.load(write(tmp_path, bad))


def test_clone_never_falls_back(tmp_path):
    cfg = C.load(write(tmp_path, {"voice": {"type": "clone", "sample": "voice/sample.wav"}}))
    no_mlx = C.Capabilities(apple_silicon=False, mlx=False, ffmpeg=True, espeak=True, playwright=True)
    with pytest.raises(C.ConfigError, match="never falls back"):
        C.effective_voice_type(cfg, no_mlx)


def test_preset_falls_back_to_system(tmp_path):
    cfg = C.load(write(tmp_path, {}))
    no_mlx = C.Capabilities(apple_silicon=False, mlx=False, ffmpeg=True, espeak=True, playwright=True)
    assert C.effective_voice_type(cfg, no_mlx) == "system"


def test_wizard_from_flags_only():
    cfg = wizard.run({"mode": "both", "voice": "system", "talking_head": True, "character": "ana",
                      "music": "sad", "outputs": ["hd", "square"], "disclosure": "end-card"}, interactive=False)
    assert cfg["mode"] == "both"
    assert cfg["talking_head"] == {"enabled": True, "character": "ana", "corner": "bottom-right"}
    assert cfg["music"]["mood"] == "sad"
    assert cfg["outputs"] == ["hd", "square"]
    assert cfg["disclosure"] == "end-card"


@pytest.mark.parametrize("flags, files", [
    (["--mode", "demo"], ["scenarios.yaml", "video.yaml"]),
    (["--mode", "explainer", "--format", "story"], ["explainer/project.json", "explainer/stories.json"]),
    (["--mode", "explainer", "--format", "montage"], ["explainer/montage.json"]),
    (["--mode", "both"], ["film.yaml"]),
])
def test_new_starters_for_every_mode(tmp_path, flags, files):
    d = tmp_path / "film"
    assert cli.main(["new", str(d), *flags, "--voice", "system", "--yes"]) == 0
    for f in files:
        assert (d / f).is_file(), f
    C.load(d)


def test_new_writes_reel_and_starters(tmp_path):
    d = tmp_path / "film"
    rc = cli.main(["new", str(d), "--mode", "demo", "--voice", "system", "--music", "calm", "--yes"])
    assert rc == 0
    cfg = C.load(d)
    assert cfg["mode"] == "demo" and cfg["music"]["mood"] == "calm"
    assert (d / "scenarios.yaml").is_file() and (d / "video.yaml").is_file()
    assert cli.main(["new", str(d), "--yes"]) == 1          # refuses to overwrite without --force


def test_demo_resolution_applies_reel_choices(tmp_path):
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({
        "tts": {"engine": "qwen"}, "presenter": {"style": "leo", "height": 0.3}, "music": {"mood": "calm"},
        "sections": [{"clip": "videos/S01.mp4", "text": "Hello."}]}))
    reel = C.load(write(tmp_path, {"mode": "demo", "voice": {"type": "system"},
                                    "talking_head": {"enabled": True, "character": "kit", "corner": "bottom-left"},
                                    "music": {"mood": "epic"}}))
    resolved, out = build._resolve_demo(reel, tmp_path)
    film = yaml.safe_load(resolved.read_text())
    assert "tts" not in film and film["voice"]["type"] == "system"
    assert film["presenter"] == {"style": "kit", "height": 0.25, "position": "bottom-left"}
    assert film["music"] == {"mood": "epic", "sync_to_scenes": True}
    assert resolved.parent == tmp_path                        # beside video.yaml, so relative clip paths still work


def test_no_music_and_no_presenter(tmp_path):
    (tmp_path / "video.yaml").write_text(yaml.safe_dump({"presenter": {"style": "leo"}, "music": {"mood": "calm"},
                                                         "sections": []}))
    reel = C.load(write(tmp_path, {"mode": "demo", "voice": {"type": "system"}, "music": {"mood": "none"}}))
    film = yaml.safe_load(build._resolve_demo(reel, tmp_path)[0].read_text())
    assert "music" not in film and "presenter" not in film


def test_stems_reach_the_pipelines(tmp_path):
    cfg = C.load(write(tmp_path, {"mode": "explainer", "outputs": ["square", "stems"]}))
    settings = build._settings(cfg, tmp_path)
    import json
    assert json.loads(settings.read_text())["outputs"] == ["stems", "hd"]     # stems, plus a master to export from


def test_stem_keeps_letters_from_non_latin_scripts():
    assert build._stem({"title": "タスク管理のご紹介"}, Path("my-film")) == "タスク管理のご紹介"
    assert build._stem({"title": "Привет мир"}, Path("my-film")) == "привет-мир"


def test_stem_falls_back_to_the_folder_name_not_film():
    assert build._stem({"title": "!!!"}, Path("my-film")) == "my-film"
    assert build._stem({"title": "😀😀"}, Path("my-film")) == "my-film"
    assert build._stem({}, Path("my-film")) == "my-film"


def test_stem_strips_path_separators_and_odd_characters():
    stem = build._stem({"title": "a/b\\c:d*e?f\"g<h>i|j"}, Path("my-film"))
    assert stem == "a-b-c-d-e-f-g-h-i-j"
    assert "/" not in stem and "\\" not in stem


def test_stem_keeps_ascii_titles_readable():
    assert build._stem({"title": "My Cool Film!"}, Path("my-film")) == "my-cool-film"
