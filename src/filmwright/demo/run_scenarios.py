"""Run a scenario file in Playwright: one fresh browser context + one real-time video per scenario.

    python -m filmwright.demo.run_scenarios <run-dir>/scenarios.yaml [--only S01,S03] [--headed] [--no-video]

Writes next to the scenario file:
    results.json, results.md      pass / fail / skip per scenario, with evidence
    videos/<id>.mp4               recording per scenario (unless --no-video): H.264 at the
                                  `recording.resolution` pixel density, real-time
    videos/<id>.events.json       when each step happened and where its target was (for zooms/callouts)
    shots/<id>-*.png              screenshots (on failure, and `screenshot:` steps)
Exit code 1 if any scenario failed. The step language is documented in docs/scenario-dsl.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import yaml
from playwright.sync_api import Locator, Page, expect, sync_playwright

from filmwright.demo.guard import check_url  # noqa: E402
from filmwright.demo.recorder import Recorder, launch_args, launch_kwargs, scale_for  # noqa: E402

# A visible pointer that follows the (scripted) mouse, with a soft glow so it reads on dark and light pages,
# a press-scale and a quick ring where each click lands, so viewers can follow what happens. Headless Chrome
# draws no cursor of its own. Everything lives in one fixed, click-through container (#__fw_fx), is animated
# with the Web Animations API / requestAnimationFrame (no <style> tag, so a strict CSP cannot block it), and is
# re-injected into every new document by add_init_script. `window.__fwCfg` ({pointer, ripple}) is prepended.
CURSOR_JS = """
(() => {
  if (window.__fwCursor) return; window.__fwCursor = true;
  const cfg = window.__fwCfg || {pointer: true, ripple: true};
  const ACCENT = '249,115,22';
  let fx = null, cur = null, dot = null, gliding = false, press = null;
  const box = () => {
    if (fx && fx.isConnected) return fx;
    fx = document.createElement('div');
    fx.id = '__fw_fx';
    Object.assign(fx.style, {position:'fixed', left:'0', top:'0', width:'0', height:'0', margin:'0', padding:'0',
      overflow:'visible', pointerEvents:'none', zIndex:2147483647});
    document.documentElement.appendChild(fx);
    cur = dot = null;
    return fx;
  };
  const pointer = () => {
    const f = box();
    if (cur && cur.isConnected) return cur;
    cur = document.createElement('div');
    cur.id = '__fw_cursor';
    Object.assign(cur.style, {position:'absolute', left:'0', top:'0', width:'0', height:'0', zIndex:2,
      pointerEvents:'none', willChange:'transform', transform:'translate3d(-40px,-40px,0)'});
    dot = document.createElement('div');
    Object.assign(dot.style, {position:'absolute', left:'-11px', top:'-11px', width:'22px', height:'22px',
      boxSizing:'border-box', borderRadius:'50%', background:'rgba(17,24,39,.55)',
      border:'2px solid rgba(255,255,255,.95)', pointerEvents:'none',
      boxShadow:'0 0 0 1px rgba(15,23,42,.30), 0 1px 5px rgba(0,0,0,.40), 0 0 14px 3px rgba(' + ACCENT + ',.32)'});
    cur.appendChild(dot);
    f.appendChild(cur);
    return cur;
  };
  const place = (x, y) => { pointer().style.transform = 'translate3d(' + x + 'px,' + y + 'px,0)'; };
  const pressDown = () => {   // shrink ~12%, spring back with a small overshoot; self-timed, as a click is over in ~100 ms
    pointer();
    if (press) press.cancel();
    press = dot.animate([
      {transform:'scale(1)', easing:'cubic-bezier(.2,.7,.3,1)'},
      {transform:'scale(.88)', offset:.24, easing:'cubic-bezier(.3,1.6,.5,1)'},
      {transform:'scale(1)'}], {duration:340});
  };
  const ripple = (x, y) => {
    const d = document.createElement('div');
    Object.assign(d.style, {position:'absolute', left:(x - 22) + 'px', top:(y - 22) + 'px', width:'44px', height:'44px',
      boxSizing:'border-box', borderRadius:'50%', border:'3px solid rgba(' + ACCENT + ',.95)',
      background:'rgba(' + ACCENT + ',.16)', pointerEvents:'none', zIndex:1, opacity:0});
    box().appendChild(d);
    const a = d.animate([{transform:'scale(.45)', opacity:1}, {transform:'scale(2.1)', opacity:0}],
      {duration:450, easing:'cubic-bezier(.15,.7,.3,1)'});
    const gone = () => d.remove();
    a.onfinish = gone; setTimeout(gone, 900);
  };
  if (cfg.pointer) {
    window.addEventListener('mousemove', (e) => { if (!gliding) place(e.clientX, e.clientY); }, true);
    // A curved, eased glide: ease-in-out along a shallow arc, a tiny overshoot past the target, then settle.
    window.__fwGlide = (x0, y0, x1, y1, ms, bow) => new Promise((resolve) => {
      const dx = x1 - x0, dy = y1 - y0, d = Math.hypot(dx, dy);
      place(x0, y0);
      if (d < 3 || ms < 60) { place(x1, y1); return resolve(); }
      const h = 2 * Math.min(0.07 * d, 40) * bow;                 // control-point offset (curve deviates h/2 from the chord)
      const cx = (x0 + x1) / 2 - dy / d * h, cy = (y0 + y1) / 2 + dx / d * h;
      const k = Math.min(0.03, 10 / d), A = 0.82;                // overshoot (<= 10 px), share of time before settling
      const prog = (u) => {
        if (u < A) { const v = u / A; return (v < .5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2) * (1 + k); }
        const v = (u - A) / (1 - A); return 1 + k * (1 - v * v * (3 - 2 * v));
      };
      let start = null, done = false;
      gliding = true;
      const finish = () => { if (done) return; done = true; gliding = false; place(x1, y1); resolve(); };
      const frame = (now) => {
        if (done) return;
        if (start === null) start = now;
        const u = Math.min((now - start) / ms, 1), b = prog(u), m = 1 - b;
        place(m * m * x0 + 2 * m * b * cx + b * b * x1, m * m * y0 + 2 * m * b * cy + b * b * y1);
        if (u < 1) requestAnimationFrame(frame); else finish();
      };
      requestAnimationFrame(frame);
      setTimeout(finish, ms + 500);                              // never hang if frames are not delivered
    });
  }
  if (cfg.ripple) {
    window.addEventListener('mousedown', (e) => { if (cfg.pointer) pressDown(); ripple(e.clientX, e.clientY); }, true);
  }
})();
"""

# Hides the recording overlay (pointer, glow, ring) in the page's own screenshots, so a failure screenshot
# never shows a half-faded ring.
SHOT_STYLE = "#__fw_fx { visibility: hidden !important; }"

VISIBLE = {"goto", "click", "hover", "fill", "type", "check", "uncheck", "select", "press", "upload"}
POINTED = {"click", "hover", "fill", "type", "check", "uncheck", "select"}
TARGETED = POINTED | {"wait_for", "expect_visible", "expect_text", "expect_count"}
SCROLL_SETTLE = 1.2   # seconds the recording rests on a page that just scrolled, before the action (a zoom eases in here)

API_JS = """
async ({path, method, body, tokenJs}) => {
  let token = null;
  try { token = tokenJs ? (new Function('return (' + tokenJs + ')'))() : null; } catch (e) {}
  const headers = {'Content-Type': 'application/json'};
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const r = await fetch(path, {method, headers, body: body == null ? undefined : JSON.stringify(body)});
  let json = null; try { json = await r.json(); } catch (e) {}
  return {status: r.status, json};
}
"""



def load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file, turning syntax errors into one readable line."""
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        sys.exit(f"{path.name} is not valid YAML{where}: {getattr(e, 'problem', e)}. "
                 "Tip: quote values that start with a quote, colon or brace, and write list indexes as .0 rather than [0] inside {…}.")
    if not isinstance(data, dict):
        sys.exit(f"{path.name} should be a YAML mapping at the top level")
    return data

class StepError(Exception):
    pass


def interpolate(value: Any, vars_: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(vars_.get(m.group(1), m.group(0))), value)
    if isinstance(value, list):
        return [interpolate(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: interpolate(v, vars_) for k, v in value.items()}
    return value


def json_path(data: Any, path: str) -> Any:
    """'data.copies[0].id' or 'data.copies.0.id'."""
    cur = data
    for part in re.findall(r"[^.\[\]]+", path):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def locate_all(page: Page, target: Any) -> Locator:
    """Every element matching a target dict (or a plain string = visible text)."""
    if isinstance(target, str):
        target = {"text": target}
    scope: Page | Locator = locate(page, target["within"]) if "within" in target else page
    exact = bool(target.get("exact", False))
    if "role" in target:
        return scope.get_by_role(target["role"], name=target.get("name"), exact=exact)
    if "testid" in target:
        return scope.get_by_test_id(target["testid"])
    if "label" in target:
        return scope.get_by_label(target["label"], exact=exact)
    if "placeholder" in target:
        return scope.get_by_placeholder(target["placeholder"], exact=exact)
    if "text" in target:
        return scope.get_by_text(target["text"], exact=exact)
    if "css" in target:
        return scope.locator(target["css"])
    raise StepError(f"target needs one of role/testid/label/placeholder/text/css: {target}")


def locate(page: Page, target: Any) -> Locator:
    """One element: `nth` if given, else the first match (keeps demos robust to duplicate labels)."""
    loc = locate_all(page, target)
    return loc.nth(int(target["nth"])) if isinstance(target, dict) and "nth" in target else loc.first


def run_step(page: Page, step: dict[str, Any], ctx: dict[str, Any]) -> str | None:
    """Execute one step; return an evidence string worth putting in the results, if any."""
    (kind, arg), = [(k, v) for k, v in step.items() if k not in ("note", "save_as")]
    arg = interpolate(arg, ctx["vars"])
    t = ctx["timeout_ms"]
    rec = ctx["recording"]
    if kind in POINTED and rec["cursor"]:
        glide(page, locate(page, arg), rec, t, ctx)

    if kind == "goto":
        page.goto(urljoin(ctx["base_url"].rstrip("/") + "/", str(arg).lstrip("/")))
        page.wait_for_load_state("networkidle", timeout=t)
        if ctx.get("recorder"):
            ctx["recorder"].kick()
    elif kind == "click":
        locate(page, arg).click(timeout=t)
    elif kind == "hover":
        locate(page, arg).hover(timeout=t)
    elif kind == "fill":
        value = str(arg["value"])
        loc = locate(page, arg)
        if rec["type_fills"] and 0 < len(value) <= 60:   # typed, so viewers see it happen
            loc.fill("", timeout=t)
            loc.press_sequentially(value, delay=rec["typing_delay_ms"], timeout=t)
        else:
            loc.fill(value, timeout=t)
    elif kind == "type":
        locate(page, arg).press_sequentially(str(arg["value"]), delay=rec["typing_delay_ms"], timeout=t)
    elif kind in ("check", "uncheck"):
        loc = locate(page, arg)
        loc.check(timeout=t) if kind == "check" else loc.uncheck(timeout=t)
    elif kind == "press":
        page.keyboard.press(str(arg))
    elif kind == "select":
        locate(page, arg).select_option(arg["option"], timeout=t)
    elif kind in ("pause", "wait"):
        page.wait_for_timeout(float(arg) * 1000)
    elif kind == "wait_for":
        locate(page, arg).wait_for(state=arg.get("state", "visible"), timeout=t)
        reveal(page, arg, ctx)
    elif kind == "expect_visible":
        expect(locate(page, arg)).to_be_visible(timeout=t)
        reveal(page, arg, ctx)
        return f"visible: {describe(arg)}"
    elif kind == "expect_hidden":
        expect(locate(page, arg)).to_be_hidden(timeout=t)
        return f"not shown: {describe(arg)}"
    elif kind == "expect_text":
        expect(locate(page, arg)).to_contain_text(str(arg["contains"]), timeout=t)
        reveal(page, arg, ctx)
        return f'"{arg["contains"]}"'
    elif kind == "expect_count":
        target = {k: v for k, v in arg.items() if k != "count"}
        expect(locate_all(page, target)).to_have_count(int(arg["count"]), timeout=t)
        reveal(page, target, ctx)
        return f'{arg["count"]} × {describe(target)}'
    elif kind == "expect_url":
        expect(page).to_have_url(re.compile(re.escape(str(arg["contains"]))), timeout=t)
        return f'url contains {arg["contains"]}'
    elif kind == "screenshot":
        path = ctx["shots"] / f'{ctx["sid"]}-{arg}.png'
        snap(page, path)
        return f"screenshot {path.name}"
    elif kind == "upload":   # set files on a (possibly hidden) <input type=file>: {css: "input[type=file]", files: ["~/a.pdf", ...]}
        paths = [os.path.expanduser(str(f)) for f in arg["files"]]
        locate(page, {k: v for k, v in arg.items() if k != "files"}).set_input_files(paths, timeout=t)
    elif kind == "eval":
        result = page.evaluate(f"() => ({arg})")
        if step.get("save_as"):
            ctx["vars"][step["save_as"]] = result
    elif kind == "api":
        return run_api(page, arg, ctx)
    else:
        raise StepError(f"unknown step '{kind}'")
    return None


def reveal(page: Page, target: Any, ctx: dict[str, Any]) -> None:
    """While recording, scroll what was just checked into view, so the viewer sees it (and a zoom can)."""
    if not ctx.get("recorder") or not ctx["recording"].get("reveal", True):
        return
    try:
        loc = locate(page, target)
        box = loc.bounding_box(timeout=2000) if loc.is_visible() else None
        vh = (page.viewport_size or {}).get("height", 810)
        if box and (box["y"] < 70 or box["y"] + box["height"] > vh - 70):   # off-screen or hugging an edge
            loc.evaluate("e => e.scrollIntoView({block: 'center', behavior: 'smooth'})")
            page.wait_for_timeout(700)
    except Exception:
        pass


def snap(page: Page, path: Path) -> None:
    """A screenshot of the page itself: the recording overlay (pointer, glow, click ring) is hidden."""
    try:
        page.screenshot(path=str(path), style=SHOT_STYLE)
    except TypeError:   # Playwright older than 1.41 has no `style` option
        page.screenshot(path=str(path))


def glide(page: Page, loc: Locator, rec: dict[str, Any], timeout: int, ctx: dict[str, Any]) -> None:
    """Glide the visible pointer to the target: an eased, slightly curved path of `glide_ms` (drawn in the page
    at display rate), then one real mouse move there so hover states fire, as before."""
    try:
        loc.scroll_into_view_if_needed(timeout=timeout)
        box = loc.bounding_box(timeout=timeout)
    except Exception:
        return
    if box:
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        x0, y0 = ctx.get("pointer") or (0.0, 0.0)           # where the pointer was left (the corner at first)
        ctx["pointer"] = (x, y)
        ctx["glides"] = ctx.get("glides", 0) + 1
        bow = 1 if ctx["glides"] % 2 else -1                 # alternate which side the path bows to
        try:
            page.evaluate("([a, b, c, d, ms, bow]) => window.__fwGlide ? window.__fwGlide(a, b, c, d, ms, bow) : null",
                          [x0, y0, x, y, max(60, rec["glide_ms"] - 14), bow])   # the page adds up to a frame at each end
        except Exception:                                    # the page navigated mid-glide; just carry on
            pass
        page.mouse.move(x, y)
        page.wait_for_timeout(120)


def bring_into_view(page: Page, step: dict[str, Any], ctx: dict[str, Any]) -> bool:
    """Scroll a pointed step's target into view before the step starts; True when that moved it.

    The click would scroll it anyway, but only after its box was logged, so a target below the fold was logged where it
    was before the scroll and its zoom aimed at the old spot (or was dropped as off-screen). Scrolling first means the
    box logged is where the action happens, and the recording shows the page there before the camera moves."""
    (kind, arg), = [(k, v) for k, v in step.items() if k not in ("note", "save_as")]
    if kind not in POINTED or not isinstance(arg, (dict, str)):
        return False
    try:
        loc = locate(page, interpolate(arg, ctx["vars"]))
        before = loc.bounding_box(timeout=1500)
        loc.scroll_into_view_if_needed(timeout=1500)
        after = loc.bounding_box(timeout=1500)
    except Exception:
        return False
    return bool(before and after and (abs(before["x"] - after["x"]) > 1 or abs(before["y"] - after["y"]) > 1))


def target_box(page: Page, step: dict[str, Any], ctx: dict[str, Any]) -> list[float] | None:
    (kind, arg), = [(k, v) for k, v in step.items() if k not in ("note", "save_as")]
    if kind not in TARGETED or not isinstance(arg, (dict, str)):
        return None
    try:
        target = interpolate(arg, ctx["vars"])
        if kind == "expect_count":
            target = {k: v for k, v in target.items() if k != "count"}
        box = locate(page, target).bounding_box(timeout=1500)
        return [round(box[k], 1) for k in ("x", "y", "width", "height")] if box else None
    except Exception:
        return None


def describe(target: Any) -> str:
    if isinstance(target, str):
        return f'"{target}"'
    for key in ("name", "text", "label", "placeholder", "testid", "css"):
        if key in target:
            return f'{target.get("role", key)} "{target[key]}"'
    return str(target)


def run_api(page: Page, arg: dict[str, Any], ctx: dict[str, Any]) -> str:
    if not page.url.startswith(("http://", "https://")):
        # api as a scenario's first step: about:blank can't resolve a relative path or send cookies
        # to the app, so load the app's origin first.
        page.goto(ctx["base_url"])
    res = page.evaluate(API_JS, {
        "path": arg["path"], "method": arg.get("method", "GET").upper(),
        "body": arg.get("body"), "tokenJs": ctx["token_js"],
    })
    want_status = arg.get("status", 200)
    if res["status"] != want_status:
        raise StepError(f'{arg["path"]} returned HTTP {res["status"]} (wanted {want_status})')
    body = res["json"]
    notes = []
    for check in arg.get("expect", []):
        path = check["path"]
        try:
            got = json_path(body, path)
        except (KeyError, IndexError, ValueError) as e:
            raise StepError(f"{path}: not in response") from e
        if "equals" in check and got != check["equals"]:
            raise StepError(f"{path} = {got!r}, expected {check['equals']!r}")
        if "contains" in check and check["contains"] not in (got if isinstance(got, (list, str)) else str(got)):
            raise StepError(f"{path} = {got!r}, expected it to contain {check['contains']!r}")
        if "length" in check and len(got) != int(check["length"]):
            raise StepError(f"{path} has {len(got)} items, expected {check['length']}")
        if check.get("truthy") and not got:
            raise StepError(f"{path} is empty/false")
        if check.get("falsy") and got:
            raise StepError(f"{path} = {got!r}, expected empty/false")
        notes.append(f"{path} ✓")
    for name, path in (arg.get("save") or {}).items():
        ctx["vars"][name] = json_path(body, path)
    return f'API {arg["path"].split("?")[0]}: ' + (", ".join(notes) if notes else f"HTTP {res['status']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios")
    ap.add_argument("--only", help="comma-separated scenario ids")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    spec_path = Path(args.scenarios).expanduser().resolve()
    spec = load_yaml(spec_path)
    root = spec_path.parent
    base_url = spec["base_url"]
    check_url(base_url, spec.get("allow_hosts"))
    auth = spec.get("auth") or {}
    state = auth.get("storage_state")
    state_path = (root / state) if state else None
    if state_path and not state_path.exists():
        print(f"No session at {state_path} — run login.py first.", file=sys.stderr)
        return 2
    vp = spec.get("viewport") or {"width": 1440, "height": 810}
    vp = {"width": int(vp["width"]) // 2 * 2, "height": int(vp["height"]) // 2 * 2}  # even, for H.264
    only = set(args.only.split(",")) if args.only else None

    videos, shots = root / "videos", root / "shots"
    videos.mkdir(exist_ok=True)
    shots.mkdir(exist_ok=True)
    results: list[dict[str, Any]] = []
    shared_vars: dict[str, Any] = dict(spec.get("vars") or {})

    rcfg = spec.get("recording") or {}
    recording = {
        "engine": str(rcfg.get("engine", "hq")),            # hq (sharp, default) | playwright (fallback)
        "resolution": str(rcfg.get("resolution", "4k")),    # 4k | 1440p | 1080p | 720p
        "fps": int(rcfg.get("fps", 30)),
        "pace": float(rcfg.get("pace", 0.8)),               # seconds of stillness after each visible action
        "cursor": bool(rcfg.get("cursor", True)),           # visible pointer that glides to each target
        "ripple": bool(rcfg.get("ripple", rcfg.get("cursor", True))),   # click ring + press-scale; on whenever the cursor is
        "glide_ms": int(rcfg.get("glide_ms", 650)),
        "typing_delay_ms": int(rcfg.get("typing_delay_ms", 70)),
        "type_fills": bool(rcfg.get("type_fills", True)),
        "reveal": bool(rcfg.get("reveal", True)),           # scroll checked elements into view
        "redact": [str(x) for x in (rcfg.get("redact") or [])],   # CSS selectors blurred in the recording
        "hide": [str(x) for x in (rcfg.get("hide") or [])],       # CSS selectors removed (display:none)
        "css": str(rcfg.get("css") or ""),                         # extra CSS injected into every page
        "init_js": (Path(os.path.expanduser(str(rcfg["init_js_file"]))).read_text() if rcfg.get("init_js_file") else ""),   # JS run before every page (privacy layers, preselecting a project)
    }
    hq = recording["engine"] == "hq" and not args.no_video
    scale = scale_for(recording["resolution"], vp["width"]) if hq else 1

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs(headless=not args.headed, slow_mo=int(spec.get("slow_mo", 100)),
                                                    args=launch_args(scale, vp) if hq else []))
        from filmwright.demo.recorder import chromium_path
        print(f"browser: {browser.version} ({'open-source Chromium' if chromium_path() else 'Chrome for Testing fallback'}), "
              f"{'recording at ' + recording['resolution'] if hq else 'no recording' if args.no_video else 'recording with Playwright'}", flush=True)
        for sc in spec["scenarios"]:
            sid = str(sc["id"])
            if only and sid not in only:
                continue
            row = {"id": sid, "area": sc.get("area", ""), "title": sc["title"],
                   "expected": sc.get("expected", ""), "status": "skip", "evidence": [], "error": None,
                   "video": None, "seconds": 0.0}
            if sc.get("skip"):
                row["error"] = str(sc["skip"])
                results.append(row)
                print(f"SKIP {sid} {sc['title']} — {sc['skip']}")
                continue
            kwargs: dict[str, Any] = {"viewport": vp, "service_workers": "block"}
            if rcfg.get("color_scheme"):   # light | dark: the page's prefers-color-scheme (apps that style some parts by the system setting look wrong otherwise)
                kwargs["color_scheme"] = str(rcfg["color_scheme"])
            if state_path:
                kwargs["storage_state"] = str(state_path)
            if not args.no_video and not hq:
                kwargs.update(record_video_dir=str(videos / "_tmp"), record_video_size=vp)
            context = browser.new_context(**kwargs)
            if recording["cursor"] or recording["ripple"]:   # overlay is re-injected into every new document
                context.add_init_script(f"window.__fwCfg = {json.dumps({'pointer': recording['cursor'], 'ripple': recording['ripple']})};"
                                        + CURSOR_JS)
            for stub in auth.get("stub_routes") or []:   # answer a request locally, e.g. an SSO heartbeat
                body = json.dumps(stub["json"]) if "json" in stub else str(stub.get("body", ""))
                context.route(str(stub["url"]), lambda route, b=body, st=int(stub.get("status", 200)),
                              ct=str(stub.get("content_type", "application/json")):
                              route.fulfill(status=st, content_type=ct, body=b))
            if recording["init_js"]:
                context.add_init_script(recording["init_js"])
            if recording["redact"] or recording["hide"] or recording["css"]:
                css = ((", ".join(recording["redact"]) + " { filter: blur(9px) !important; } ") if recording["redact"] else "") + \
                      ((", ".join(recording["hide"]) + " { display: none !important; } ") if recording["hide"] else "") + recording["css"]
                context.add_init_script("(() => { const add = () => { const s = document.createElement('style'); "
                                        f"s.textContent = {json.dumps(css)}; document.documentElement.appendChild(s); }}; "
                                        "if (document.documentElement) add(); else document.addEventListener('DOMContentLoaded', add); })();")
            page = context.new_page()
            ctx = {"base_url": base_url, "timeout_ms": int(spec.get("default_timeout", 15)) * 1000,
                   "token_js": auth.get("token_js"), "vars": shared_vars, "shots": shots, "sid": sid,
                   "recording": recording, "recorder": None}
            page.set_default_timeout(ctx["timeout_ms"])
            recorder = None
            if hq:
                recorder = Recorder(context, page, videos / f"{sid}.mp4", vp, scale, fps=recording["fps"])
                recorder.start()
                ctx["recorder"] = recorder
            events: list[dict[str, Any]] = []
            start = time.time()
            try:
                for i, step in enumerate(sc.get("steps", []), 1):
                    kind = next(k for k in step if k not in ("note", "save_as"))
                    ready = None
                    if kind in POINTED and bring_into_view(page, step, ctx) and recorder:
                        ready = time.time()                     # the page is where the action will happen from here
                        page.wait_for_timeout(SCROLL_SETTLE * 1000)
                    began = time.time()
                    box = target_box(page, step, ctx) if kind in POINTED else None
                    try:
                        ev = run_step(page, step, ctx)
                    except Exception as e:  # noqa: BLE001 — every failure becomes a result row
                        msg = str(e).splitlines()[0] if str(e) else type(e).__name__
                        raise StepError(f"step {i} ({kind}): {msg}") from e
                    if kind in TARGETED and box is None:
                        box = target_box(page, step, ctx)
                    arg = step[kind]
                    events.append({"step": i, "kind": kind, "t": began, "end": time.time(),
                                   "evidence": ev if kind == "api" else None,
                                   "label": describe(interpolate(arg, ctx["vars"])) if kind in TARGETED else
                                   (str(interpolate(arg, ctx["vars"])) if kind in ("goto", "press") else ""),
                                   "box": box, **({"ready": ready} if ready else {})})
                    if ev:
                        row["evidence"].append(ev)
                    if kind in VISIBLE and recording["pace"] > 0:
                        page.wait_for_timeout(recording["pace"] * 1000)
                page.wait_for_timeout(float(sc.get("hold", 2.0)) * 1000)  # end on a readable frame
                row["status"] = "pass"
            except StepError as e:
                row["status"] = "fail"
                row["error"] = str(e)
                try:
                    shot = shots / f"{sid}-failure.png"
                    snap(page, shot)
                    row["evidence"].append(f"screenshot {shot.name}")
                except Exception:
                    pass
                if spec.get("debug"):
                    traceback.print_exc()
            row["seconds"] = round(time.time() - start, 1)
            if recorder:
                out = recorder.stop()
                for e in events:
                    e["t"], e["end"] = recorder.rel(e["t"]), recorder.rel(e["end"])
                    if e.get("ready"):
                        e["ready"] = recorder.rel(e["ready"])
                if out:
                    row["video"] = str(out.relative_to(root))
                    (videos / f"{sid}.events.json").write_text(json.dumps({
                        "viewport": vp, "scale": scale, "frame": [vp["width"] * scale, vp["height"] * scale],
                        **({"captured": [list(d) for d in recorder.mismatched()]} if recorder.mismatched() else {}),
                        "events": events}, indent=1))
            video = page.video
            context.close()  # finalizes Playwright's webm, if that engine is in use
            if video and not recorder:
                dest = videos / f"{sid}.webm"
                shutil.move(video.path(), dest)
                row["video"] = str(dest.relative_to(root))
            results.append(row)
            mark = {"pass": "PASS", "fail": "FAIL"}[row["status"]]
            print(f"{mark} {sid} {sc['title']}" + (f" — {row['error']}" if row["error"] else ""))
        browser.close()
    shutil.rmtree(videos / "_tmp", ignore_errors=True)

    if only and (root / "results.json").exists():   # --only: update those rows, keep the rest of the table
        fresh = {r["id"]: r for r in results}
        previous = json.loads((root / "results.json").read_text())
        merged = [fresh.pop(r["id"], r) for r in previous]
        results = merged + list(fresh.values())
    (root / "results.json").write_text(json.dumps(results, indent=2))
    icon = {"pass": "✅ Pass", "fail": "❌ Fail", "skip": "⏭️ Skipped"}
    lines = [f"# {spec.get('name', 'Scenario results')}", "",
             f"Environment: {base_url} · {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| # | Area | Scenario | Expected | Result | Evidence |", "|---|---|---|---|---|---|"]
    for r in results:
        detail = r["error"] if r["status"] != "pass" else "; ".join(r["evidence"][:4])
        cells = [r["id"], r["area"], r["title"], r["expected"], icon[r["status"]], detail or ""]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    counts = {k: sum(1 for r in results if r["status"] == k) for k in ("pass", "fail", "skip")}
    lines += ["", f"**{counts['pass']} passed · {counts['fail']} failed · {counts['skip']} skipped**"]
    (root / "results.md").write_text("\n".join(lines) + "\n")
    print(f"\n{counts['pass']} passed, {counts['fail']} failed, {counts['skip']} skipped → {root / 'results.md'}")
    return 1 if counts["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
