"""The recorder refuses a saved session whose access token has expired (the recording would show the app signed out)."""
import base64
import json
import time

from filmwright.demo.run_scenarios import session_minutes_left


def jwt(claims: dict) -> str:
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64(claims)}.sig"


def state(tmp_path, local=None, cookies=None):
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"cookies": cookies or [],
                             "origins": [{"origin": "https://app.example", "localStorage": [{"name": k, "value": v} for k, v in (local or {}).items()]}]}))
    return p


def test_reads_the_named_token_from_local_storage(tmp_path):
    now = time.time()
    p = state(tmp_path, {"auth_token": jwt({"exp": now + 1800}), "refresh_token": jwt({"exp": now + 86400, "type": "refresh"})})
    left = session_minutes_left(p, "localStorage.getItem('auth_token')")
    assert 29 < left <= 30


def test_an_expired_token_is_negative(tmp_path):
    p = state(tmp_path, {"auth_token": jwt({"exp": time.time() - 600})})
    assert session_minutes_left(p, "localStorage.getItem('auth_token')") < -9


def test_without_a_key_name_refresh_tokens_are_ignored(tmp_path):
    now = time.time()
    p = state(tmp_path, {"access": jwt({"exp": now + 600}), "refresh": jwt({"exp": now + 86400, "type": "refresh"})})
    left = session_minutes_left(p)
    assert 9 < left <= 10


def test_cookies_count_too(tmp_path):
    p = state(tmp_path, cookies=[{"name": "session", "value": jwt({"exp": time.time() + 3000})}])
    assert 49 < session_minutes_left(p) <= 50


def test_unknown_when_nothing_looks_like_a_jwt(tmp_path):
    assert session_minutes_left(state(tmp_path, {"theme": "dark", "token": "opaque-value"})) is None
    assert session_minutes_left(tmp_path / "missing.json") is None


def test_the_runner_refuses_an_expired_session_before_recording(tmp_path, monkeypatch, capsys):
    import sys

    import yaml

    from filmwright.demo import run_scenarios
    state(tmp_path, {"auth_token": jwt({"exp": time.time() - 600})})
    (tmp_path / "scenarios.yaml").write_text(yaml.safe_dump({
        "base_url": "http://localhost:3000/", "auth": {"storage_state": "auth.json", "token_js": "localStorage.getItem('auth_token')"},
        "scenarios": [{"id": "S01", "title": "t", "steps": [{"goto": "/"}]}]}))
    monkeypatch.setattr(sys, "argv", ["run_scenarios", str(tmp_path / "scenarios.yaml")])
    assert run_scenarios.main() == 2
    assert "expired 10 min ago" in capsys.readouterr().err
    assert not (tmp_path / "videos").exists()           # stopped before anything was recorded


def test_build_passes_allow_expired_to_the_runner(tmp_path, monkeypatch):
    from filmwright import build
    (tmp_path / "scenarios.yaml").write_text("scenarios: []\n")
    calls = []
    monkeypatch.setattr(build, "_run", lambda *a, **k: calls.append(a) or 1)
    reel = {"demo": {"scenarios": "scenarios.yaml"}}
    build.build_demo(reel, tmp_path, None, False, allow_expired=True)
    build.build_demo(reel, tmp_path, None, False)
    assert "--allow-expired" in calls[0] and "--allow-expired" not in calls[1]
