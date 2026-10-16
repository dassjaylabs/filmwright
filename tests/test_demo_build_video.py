from filmwright.demo.build_video import NARRATION_LUFS, music_plan, sentences, srt_time, voice_config


def test_voice_block_is_passed_through():
    cfg = {"voice": {"type": "described", "description": "Calm narrator"}}
    assert voice_config(cfg) == {"type": "described", "description": "Calm narrator"}


def test_older_tts_block_maps_to_voice_types():
    assert voice_config({"tts": {"engine": "espeak-ng", "voice": "en-gb", "rate": 150}}) == \
        {"type": "system", "system_voice": "en-gb", "rate": 150}
    assert voice_config({"tts": {"engine": "qwen", "mode": "custom", "speaker": "aiden", "instruct": "Warm"}}) == \
        {"type": "preset", "style": "Warm", "speaker": "aiden"}
    assert voice_config({"tts": {"engine": "qwen", "mode": "design", "instruct": "Calm voice"}}) == \
        {"type": "described", "description": "Calm voice"}
    assert voice_config({}) == {}


def test_music_plan():
    assert music_plan({}) is None
    assert music_plan({"music": {"mood": "none"}}) is None
    p = music_plan({"music": "upbeat"})
    assert p["mood"] == "upbeat" and p["sync_to_scenes"] is True and p["level_lufs"] == NARRATION_LUFS - 20   # a score
    assert music_plan({"music": {"mood": "calm", "sync_to_scenes": False}})["level_lufs"] == NARRATION_LUFS - 26   # a bed
    assert music_plan({"music": {"mood": "calm", "level": -10}})["level_lufs"] == NARRATION_LUFS - 10
    assert music_plan({"music": {"mood": "calm", "level_lufs": -35}})["level_lufs"] == -35


def test_sentences_and_srt_time():
    assert sentences("One. Two? Three!  Four: five") == ["One.", "Two?", "Three!", "Four:", "five"]
    assert srt_time(3725.5) == "01:02:05,500"
