import json
from pathlib import Path

import pytest
import yaml

from filmwright import build
from filmwright.core.names import checked_slug, file_safe
from filmwright.explainer.montage import EXAMPLE as MONTAGE_EXAMPLE
from filmwright.explainer.montage import Montage
from filmwright.explainer.story import Project, init_project
from filmwright.hybrid.film import Film

UNSAFE = "Acme/Tasks: *Tour?* [beta] ../x"


def test_unsafe_characters_become_single_dashes():
    assert file_safe(UNSAFE) == "acme-tasks-tour-beta-x"
    assert file_safe("a\\b\x00c\nd|e<f>g\"h") == "a-b-c-d-e-f-g-h"


def test_any_script_is_kept():
    assert file_safe("タスク管理のご紹介") == "タスク管理のご紹介"
    assert file_safe("Привет мир") == "привет-мир"
    assert file_safe("مرحبا بالعالم") == "مرحبا-بالعالم"


def test_both_ways_of_typing_an_accent_give_one_name():
    composed, decomposed = "Café", "Café"
    assert composed != decomposed
    assert file_safe(composed) == file_safe(decomposed) == "café"
    assert build._stem({"title": decomposed}, Path("x")) == build._stem({"title": composed}, Path("x"))


def test_case_is_kept_when_asked_and_nothing_usable_gives_empty():
    assert file_safe("Acme-Tour", lower=False) == "Acme-Tour"
    assert file_safe("!!! 😀") == "" and file_safe(None) == ""
    assert len(file_safe("あ" * 90)) == 60


def test_story_names_and_folders_are_file_safe(tmp_path):
    init_project(tmp_path)
    cfg = json.loads((tmp_path / "project.json").read_text())
    cfg.pop("file_prefix", None)
    cfg["product"] = "Acme/Tasks?"
    (tmp_path / "project.json").write_text(json.dumps(cfg))
    p = Project(tmp_path)
    c = dict(p.stories[1], slug="../../outside")
    assert p.stem(c) == "acme-tasks-outside"
    assert p.outdir(c).parent == tmp_path and p.outdir(c).name == "01-outside"
    assert p.stem(dict(c, slug="!!!")) == "acme-tasks-story-1"


def test_montage_name_is_file_safe(tmp_path):
    cfg = json.loads(MONTAGE_EXAMPLE.read_text())
    cfg.pop("file_prefix", None)
    cfg["product"] = "Acme: Tasks*"
    (tmp_path / "montage.json").write_text(json.dumps(cfg))
    assert Montage(tmp_path).stem == "acme-tasks-montage"


def test_hybrid_prefix_is_file_safe(tmp_path):
    spec = tmp_path / "film.yaml"
    spec.write_text(yaml.safe_dump({"file_prefix": "Acme/Tour[1]", "segments": [{"scene": "title", "say": "Hi."}]}))
    assert Film(spec).stem == "Acme-Tour-1"


def test_examples_keep_their_names(tmp_path):
    init_project(tmp_path)
    p = Project(tmp_path)
    assert p.stem(p.stories[1]) == "acme-tasks-support-on-call-rota"


def test_series_slugs_must_already_be_file_safe():
    assert checked_slug("boards") == "boards"
    assert checked_slug("ボード") == "ボード"
    for bad in ("../boards", "my boards", "", None, "a/b"):
        with pytest.raises(ValueError, match="can't be used in a file name"):
            checked_slug(bad)
    with pytest.raises(ValueError, match="'my-boards'"):
        checked_slug("my boards")
