
from PIL import Image

from filmwright import storyboard as SB
from filmwright.explainer.render import board_panels


def test_timecode():
    assert [SB.timecode(x) for x in (0, 4.4, 59.6, 61, 125)] == ["0:00", "0:04", "1:00", "1:01", "2:05"]


def test_panels_run_until_the_next_scene(tmp_path):
    beats = [{"key": "intro", "text": "Hi.", "start": 0.6, "dur": 2.0}, {"key": "f1", "text": "One.", "start": 4.0, "dur": 1.5}]
    p = board_panels(beats, 9.0, [tmp_path / "a.png", tmp_path / "b.png"], {"f1": "Feature one"})
    assert [(x["label"], x["start"], x["dur"]) for x in p] == [("Intro", 0.0, 4.0), ("Feature one", 4.0, 5.0)]


def test_page_escapes_text_and_shows_placeholders(tmp_path):
    img = tmp_path / "still.png"
    Image.new("RGB", (1920, 1080), "navy").save(img)
    groups = [{"heading": "", "panels": [
        {"label": "Intro <b>", "start": 0, "dur": 4, "text": "Fish & chips", "image": str(img)},
        {"label": "Card", "start": 4, "dur": 3, "text": "", "image": "", "placeholder": "title card"}]}]
    page = SB.render_html("Demo", {"Voice": "library · olivia"}, groups, tmp_path / "board")
    html = page.read_text()
    assert "Intro &lt;b&gt;" in html and "Fish &amp; chips" in html and "title card" in html
    assert (tmp_path / "board" / "img" / "001.jpg").is_file() and "Approved by" in html
    assert "0:00–0:04" in html and "0:04–0:07" in html


def test_demo_board_needs_no_narration_or_recordings(tmp_path):
    film = {"title_card": {"title": "Your week"}, "intro": "This is Acme Tasks.",
            "sections": [{"clip": "videos/S01.mp4", "label": "1 · This week", "text": "Everything due this week sits in one list."}],
            "closing_card": {"title": "That's it", "bullets": ["One list"]}, "outro": "Plan less."}
    panels = SB.demo_groups(film, tmp_path, tmp_path / "frames")[0]["panels"]
    assert [p["label"] for p in panels] == ["Title card", "1 · This week", "Closing card"]
    assert panels[1]["image"] == "" and panels[1]["start"] == panels[0]["dur"]
    assert panels[0]["on_screen"] == "Your week" and panels[2]["on_screen"] == "That's it · One list"
