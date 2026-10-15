import numpy as np
import pytest

from filmwright.core.voice import qwen as Q
from filmwright.core.voice.qwen import MIN_SCORE, match_score, speech_seconds, words


@pytest.mark.parametrize("expected, heard", [
    ("今日は良い天気です。", "ラーメンが食べたい。"),          # Japanese
    ("这个按钮会分享任务。", "我们明天见。"),                  # Chinese
    ("안녕하세요", "감사합니다"),                              # Korean
    ("Привет, мир", "Пока"),                                  # Russian
])
def test_unrelated_lines_in_other_scripts_fail(expected, heard):
    assert match_score(expected, heard) < MIN_SCORE


@pytest.mark.parametrize("expected, heard", [
    ("今日は良い天気です。", "今日は良い天気です"),
    ("Café crème brûlée.", "Cafe creme brulee"),               # Whisper may drop accents
    ("Grüße aus München!", "Grüsse aus Munchen"),
    ("Acme Tasks is ready.", "acme tasks is ready"),
    ("ＡＣＭＥ　Ｔａｓｋｓ", "ACME Tasks"),                       # full-width forms
])
def test_matching_lines_pass(expected, heard):
    assert match_score(expected, heard) >= MIN_SCORE


def test_nothing_to_compare_is_never_a_free_pass():
    assert match_score("...", "...") == 0.0
    assert match_score("Hello there.", "") == 0.0


def test_words_keep_every_script():
    assert words("今日は") == ["今日は"]
    assert words("Don't stop, it's 3!") == ["don't", "stop", "it's", "3"]


def test_spoken_length_counts_characters_where_there_are_no_spaces():
    jp = "このボタンを押すと、すべてのタスクがチームの全員に共有されます。"
    assert speech_seconds(jp) > 4.0                       # was 1.0 s, so every real take looked "runaway"
    assert 3.0 < speech_seconds("Pick a mood, choose your outputs, and filmwright builds the whole film.") < 6.0


def _take(spoken: float, rate: int = 24000, pad: float = 0.3):
    """A fake take: `spoken` seconds of tone between `pad` seconds of silence."""
    t = np.arange(int(spoken * rate)) / rate
    tone = 0.3 * np.sin(2 * np.pi * 180 * t).astype(np.float32)
    gap = np.zeros(int(pad * rate), np.float32)
    return np.concatenate([gap, tone, gap])


def test_spoken_seconds_leaves_out_silence():
    assert abs(Q.spoken_seconds(_take(2.0), 24000) - 2.0) < 0.02
    assert Q.spoken_seconds(np.zeros(24000, np.float32), 24000) == 0.0


def _voice(takes, tmp_path):
    v = object.__new__(Q.QwenVoice)
    v.seed, v.verify, v.report, v.slow = 7, False, [], []
    v.model = type("M", (), {"sample_rate": 24000})()
    queue = list(takes)
    v._generate = lambda text, mode, seed: queue.pop(0)
    return v, queue


def test_a_drawn_out_take_is_regenerated(tmp_path):
    text = "Show every feature in a minute, on any screen."          # about 3.5 s at a normal pace
    normal = Q.speech_seconds(text)
    v, queue = _voice([_take(normal * 1.6), _take(normal * 0.95)], tmp_path)
    v._render(text, tmp_path / "out.wav", "custom")
    assert not queue and not v.slow
    assert abs(Q.wav_seconds(tmp_path / "out.wav") - (normal * 0.95 + 0.6)) < 0.05


def test_the_least_drawn_out_take_is_kept_and_reported(tmp_path):
    text = "Show every feature in a minute, on any screen."
    normal = Q.speech_seconds(text)
    v, queue = _voice([_take(normal * 1.9), _take(normal * 1.4), _take(normal * 1.7)], tmp_path)
    v._render(text, tmp_path / "out.wav", "custom")
    assert not queue
    assert abs(Q.wav_seconds(tmp_path / "out.wav") - (normal * 1.4 + 0.6)) < 0.05
    assert [s for s, _ in v.slow] == [text]
