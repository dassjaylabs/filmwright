"""Directed effects for build_video.py: zooms, callouts and spotlights, anchored to what the runner logged.

`run_scenarios.py` writes `videos/<id>.events.json` next to each recording. It holds every step's time
(seconds into the clip) and its target's box in CSS px. A section in video.yaml then directs the camera:

    focus:      [{target: 'button "Save"', hold: 2.5}, {step: 4, zoom: 1.6}, {box: [x, y, w, h], at: 6}]
    callouts:   [{target: "status-banner", text: "Appears only when the record changed", duration: 3}]
    spotlight:  [{target: 'dialog "Confirm changes"', duration: 3}]

`target` matches an event label (the step's target, e.g. `button "Save"`) case-insensitively. `step` is the
step number in the scenario. `box` is CSS px, and with it `at` is required.

Zooms are eased and hold for at least 2 s; back-to-back zooms pan from one target to the next instead
of zooming out in between. The zoom level is fitted to the target (a wide banner gets less) unless
`zoom` is given; a target too big to zoom on is skipped with a note (use a spotlight instead).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

RAMP = 0.7                 # seconds to ease in or out
MIN_HOLD = 2.0             # a zoom stays in at least this long
ACCENT = (249, 115, 22)    # matches the click ripple


def load_events(clip: Path) -> dict[str, Any] | None:
    p = clip.with_name(clip.stem + ".events.json")
    return json.loads(p.read_text()) if p.exists() else None


def loading_cuts(meta: dict[str, Any] | None, min_len: float = 2.0) -> list[tuple[float, float]]:
    """Spans of page loading worth cutting: any `goto` that took longer than `min_len`. A load at the very
    start is cut from 0, so the section opens on the loaded page; later loads keep a short glimpse."""
    cuts = []
    if not meta:
        return cuts
    visible_before = False
    for e in meta["events"]:
        if e["kind"] == "goto" and e["end"] - e["t"] > min_len:
            a = 0.0 if not visible_before else e["t"] + 0.4
            cuts.append((a, max(a, e["end"] - 0.5)))
        if e["kind"] not in ("api", "eval"):
            visible_before = True
    return cuts


def remap(meta: dict[str, Any] | None, cuts: list[tuple[float, float]]) -> dict[str, Any] | None:
    """Event times after the cuts are removed (an event inside a cut lands where the cut was)."""
    if not meta or not cuts:
        return meta
    def shift(t: float) -> float:
        return t - sum(min(max(0.0, t - a), b - a) for a, b in cuts)
    events = [{**e, "t": round(shift(e["t"]), 3), "end": round(shift(e["end"]), 3),
               **({"ready": round(shift(e["ready"]), 3)} if e.get("ready") is not None else {})} for e in meta["events"]]
    return {**meta, "events": events}


def find_event(events: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any] | None:
    if "step" in spec:
        hits = [e for e in events if e["step"] == int(spec["step"])]
    elif any(k in spec for k in ("target", "on", True)):   # YAML 1.1 reads a bare `on:` key as True
        needle = str(spec.get("target", spec.get("on", spec.get(True)))).lower()
        hits = [e for e in events if e.get("box") and needle in (e.get("label") or "").lower()]
    else:
        return None
    hits = hits[int(spec.get("nth", 0)):]
    return hits[0] if hits else None


def resolve(spec: dict[str, Any], ev: dict[str, Any] | None, factor: float) -> tuple[float, list[float]] | None:
    """(time in s, box in frame px) for a focus / callout / spotlight spec."""
    if "box" in spec:
        if "at" not in spec:
            return None
        return float(spec["at"]), [float(v) * factor for v in spec["box"]]
    data = ev and ev.get("box")
    if not data:
        return None
    t = float(spec["at"]) if "at" in spec else float(ev["t"])
    return t, [v * factor for v in data]


ACTION_KINDS = ("click", "hover", "fill", "type", "check", "select", "press")


def auto_focus_specs(section: dict[str, Any], meta: dict[str, Any] | None, log: Any = print) -> list[dict[str, Any]]:
    """Zoom specs for the real actions in a clip: clicks, hovers, typing, ticks. Each becomes a focus window with an
    explicit zoom and centre (so a wide card is not skipped as "fills the screen": we zoom on its left part instead).

    Section options: auto_focus (true | "add"), auto_focus_max (default 3), auto_focus_zoom (max, default 1.9),
    auto_focus_hold (default 2.6), auto_focus_skip: [step numbers]."""
    if not meta:
        return []
    vw, vh = meta["viewport"]["width"], meta["viewport"]["height"]
    evs = [e for e in meta["events"] if e.get("box") and e["t"] > 2.5]
    allev = meta["events"]
    cap = int(section.get("auto_focus_max", 3))
    zmax = float(section.get("auto_focus_zoom", 1.9))
    hold = float(section.get("auto_focus_hold", 2.6))
    skip = set(section.get("auto_focus_skip") or [])
    cands = []
    for e in evs:
        if e["kind"] not in ACTION_KINDS or e.get("step") in skip:
            continue
        x, y, w, h = e["box"]
        if w <= 0 or h <= 0 or w * h > 0.8 * vw * vh:
            continue
        # does this action navigate? (a goto / expect_url follows within 3.5 s)
        nav = any(n["kind"] in ("expect_url", "goto") and 0 < n["t"] - e["t"] < 3.5 for n in allev)
        small = w <= 0.45 * vw and h <= 0.25 * vh
        if small:
            z, box = min(zmax, max(1.5, 0.36 * vw / w)), [x, y, w, h]
        else:                                           # wide card / region: zoom on its upper-left part, where the headline is
            ww, hh = min(w, 640.0), min(h, 200.0)
            z, box = min(zmax, 1.65), [x, y, ww, hh]
        weight = {"click": 3, "fill": 3, "type": 3, "select": 3, "check": 3, "press": 2, "hover": 1}[e["kind"]]
        cands.append({"t": e["t"], "weight": weight, "nav": nav, "box": box, "zoom": round(z, 2), "kind": e["kind"],
                      "step": e.get("step"), "ready": e.get("ready")})
    # scrolls are actions too: when the page has scrolled to new content, push in on the content as it settles
    for e in allev:
        if e["kind"] == "eval" and e["t"] > 2.0 and e.get("step") not in skip and not e.get("box"):
            cands.append({"t": e["end"] + 0.25, "weight": 0.5, "nav": False, "kind": "scroll", "step": e.get("step"),
                          "box": [110.0, 190.0, 900.0, 400.0], "zoom": round(min(zmax, float(section.get("auto_focus_scroll_zoom", 1.45))), 2)})
    # greedy by time, keeping windows apart; prefer stronger actions when there are more candidates than room
    cands.sort(key=lambda c: (-c["weight"], c["t"]))
    chosen: list[dict[str, Any]] = []
    for c in cands:
        if len(chosen) >= cap:
            break
        if all(abs(c["t"] - k["t"]) >= 3.8 for k in chosen):
            chosen.append(c)
    chosen.sort(key=lambda c: c["t"])
    out = []
    for c in chosen:
        lead = 1.6 if c["nav"] else 0.9               # land the zoom just before the action; a navigating click zooms out as it fires
        lead_c = 0.2 if c["kind"] == "scroll" else lead          # scroll: the zoom starts as the page settles
        at = c["t"] - lead_c
        if c.get("ready") is not None:                 # the page scrolled to the target: don't move in before it is there
            at = max(at, c["ready"] + 0.25)            # plan_camera starts the ease 0.25 s before `at`
        out.append({"box": c["box"], "at": round(max(0.0, at), 2), "zoom": c["zoom"], "hold": 1.9 if c["nav"] else hold})
    return out


def plan_camera(section: dict[str, Any], meta: dict[str, Any] | None, frame: tuple[int, int],
                log: Any = print) -> list[tuple[float, float, float, float]]:
    """Keyframes (t, zoom, cx, cy) in frame px. Empty when the section has no focus."""
    specs = list(section.get("focus") or [])
    af = section.get("auto_focus", True)          # on by default: zoom in on the clip's actions; `auto_focus: false` turns it off
    if af and (af == "add" or not specs):
        specs += auto_focus_specs(section, meta, log)
        if specs:
            log(f"  auto-focus: {len([s_ for s_ in specs if 'zoom' in s_])} zoom(s) on the clip's actions")
    if not specs:
        return []
    fw, fh = frame
    factor = fw / meta["viewport"]["width"] if meta else 1.0
    events = meta["events"] if meta else []
    wins = []
    for spec in specs:
        r = resolve(spec, find_event(events, spec), factor)
        if not r:
            log(f"  focus {spec}: no matching event with a target box, skipped")
            continue
        t, (x, y, w, h) = r
        if not (0 <= x + w / 2 <= fw and 0 <= y + h / 2 <= fh):
            log(f"  focus {spec}: target was off-screen at that moment, skipped")
            continue
        z = float(spec["zoom"]) if "zoom" in spec else min(float(spec.get("max_zoom", 1.8)), fw / (w * 1.25), fh / (h * 2.6))
        if z < 1.15:
            log(f"  focus {spec}: target fills most of the screen, zoom skipped (use a spotlight)")
            continue
        wins.append((max(0.0, t - 0.25), z, x + w / 2, y + h / 2, max(MIN_HOLD, float(spec.get("hold", 2.5)))))
    wins.sort()
    cx0, cy0 = fw / 2, fh / 2
    kf: list[tuple[float, float, float, float]] = [(0.0, 1.0, cx0, cy0)]
    for a, z, cx, cy, hold in wins:
        last = kf[-1]
        if last[1] == 1.0 and len(kf) > 1 and a < last[0]:
            kf.pop()                                   # still zoomed in: pan straight to the next target
            t_in = max(a, kf[-1][0]) + RAMP
        else:
            a = max(a, last[0])
            if a > last[0]:
                kf.append((a, 1.0, cx0, cy0))
            t_in = a + RAMP
        kf += [(t_in, z, cx, cy), (t_in + hold, z, cx, cy), (t_in + hold + RAMP, 1.0, cx0, cy0)]
    return kf


def _piecewise(kf: list[tuple[float, ...]], idx: int) -> str:
    """ffmpeg expression of input time `it`, smoothstep-interpolated between keyframes."""
    expr = f"{kf[-1][idx]:.4f}"
    for (t0, *v0), (t1, *v1) in reversed(list(zip(kf, kf[1:]))):
        a, b = v0[idx - 1], v1[idx - 1]
        u = f"clip((it-{t0:.3f})/{max(1e-3, t1 - t0):.3f},0,1)"
        seg = f"({a:.4f}+({b - a:.4f})*{u}*{u}*(3-2*{u}))"
        expr = f"if(lt(it,{t1:.3f}),{seg},{expr})"
    return expr


def zoompan(kf: list[tuple[float, float, float, float]], out_w: int, out_h: int, fps: int) -> str:
    z = _piecewise(kf, 1)
    cx, cy = _piecewise(kf, 2), _piecewise(kf, 3)
    x = f"clip({cx}-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip({cy}-ih/zoom/2,0,ih-ih/zoom)"
    return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={out_w}x{out_h}:fps={fps}"


def _font(size: int) -> Any:
    from filmwright.demo.build_video import font  # same font discovery as the cards
    return font(size, True)


def _padded(box: list[float], pad: float, fw: int, fh: int) -> list[float]:
    x, y, w, h = box
    return [max(0, x - pad), max(0, y - pad), min(fw, x + w + pad), min(fh, y + h + pad)]


def callout_png(frame: tuple[int, int], box: list[float], text: str, scale: float, out: Path) -> None:
    """Accent outline around the target and a dark label bubble beside it, at frame resolution."""
    fw, fh = frame
    im = Image.new("RGBA", frame, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = _padded(box, 8 * scale, fw, fh)
    d.rounded_rectangle([x0, y0, x1, y1], radius=10 * scale, outline=ACCENT + (255,), width=max(2, int(3 * scale)))
    f = _font(int(17 * scale))
    pad, maxw = 12 * scale, 380 * scale
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if d.textlength(trial, font=f) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    lines += [cur] if cur else []
    lh = int(17 * scale * 1.35)
    bw = max(d.textlength(ln, font=f) for ln in lines) + 2 * pad
    bh = lh * len(lines) + 2 * pad
    gap = 14 * scale
    below = y1 + gap + bh < fh - 20 * scale
    by = y1 + gap if below else max(20 * scale, y0 - gap - bh)
    bx = min(max(20 * scale, x0), fw - bw - 20 * scale)
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=10 * scale, fill=(17, 24, 39, 235))
    tip_x = min(max(bx + 18 * scale, (x0 + x1) / 2), bx + bw - 18 * scale)
    if below:
        d.polygon([(tip_x - 9 * scale, by), (tip_x + 9 * scale, by), (tip_x, by - 9 * scale)], fill=(17, 24, 39, 235))
    else:
        d.polygon([(tip_x - 9 * scale, by + bh), (tip_x + 9 * scale, by + bh), (tip_x, by + bh + 9 * scale)],
                  fill=(17, 24, 39, 235))
    for k, ln in enumerate(lines):
        d.text((bx + pad, by + pad + k * lh), ln, font=f, fill=(255, 255, 255, 255))
    im.save(out)


def spotlight_png(frame: tuple[int, int], box: list[float], scale: float, out: Path) -> None:
    """Dim everything except the target."""
    fw, fh = frame
    alpha = Image.new("L", frame, 120)
    x0, y0, x1, y1 = _padded(box, 10 * scale, fw, fh)
    ImageDraw.Draw(alpha).rounded_rectangle([x0, y0, x1, y1], radius=12 * scale, fill=0)
    im = Image.new("RGBA", frame, (8, 10, 14, 0))
    im.putalpha(alpha)
    ImageDraw.Draw(im).rounded_rectangle([x0, y0, x1, y1], radius=12 * scale, outline=ACCENT + (230,),
                                         width=max(2, int(2.5 * scale)))
    im.save(out)


def phrase_png(frame: tuple[int, int], text: str, scale: float, out: Path, pos: str = "top-left") -> None:
    """A key-phrase chip: an accent bar and bold text on a dark rounded plate, for the number or idea the
    narration is mentioning right now."""
    fw, fh = frame
    im = Image.new("RGBA", frame, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font(int(30 * scale))
    pad_x, pad_y, bar = 22 * scale, 14 * scale, 7 * scale
    tw = d.textlength(text, font=f)
    bw, bh = tw + 2 * pad_x + bar, 30 * scale * 1.3 + 2 * pad_y
    m = 36 * scale
    x = {"left": m, "center": (fw - bw) / 2, "right": fw - bw - m}[pos.split("-")[-1] if pos.split("-")[-1] in ("left", "right") else "center"]
    y = (fh - bh - m * 2.2) if pos.startswith("bottom") else (m * 2.6)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=14 * scale, fill=(15, 18, 34, 238))
    d.rounded_rectangle([x, y, x + bar, y + bh], radius=3 * scale, fill=ACCENT + (255,))
    d.text((x + bar + pad_x, y + pad_y), text, font=f, fill=(238, 242, 247, 255))
    im.save(out)


def aim_points(section: dict[str, Any], meta: dict[str, Any] | None, frame: tuple[int, int]) -> list[tuple[float, float, float]]:
    """(time, x, y) in frame px for every callout and spotlight, so the host can point at them. Zooms are
    handled separately; this covers wide targets whose zoom is skipped."""
    out: list[tuple[float, float, float]] = []
    if not meta:
        return out
    factor = frame[0] / meta["viewport"]["width"]
    for kind in ("spotlight", "callouts"):
        for spec in section.get(kind) or []:
            r = resolve(spec, find_event(meta["events"], spec), factor)
            if not r:
                continue
            tt, (x, y, w, h) = r
            if 0 <= x + w / 2 <= frame[0] and 0 <= y + h / 2 <= frame[1]:
                out.append((tt, x + w / 2, y + h / 2))
    return sorted(out)


KEY_NAMES = {"Escape": "Esc", "Enter": "Enter ⏎", "Tab": "Tab ⇥", "Backspace": "⌫", "ArrowDown": "↓", "ArrowUp": "↑",
             "ArrowLeft": "←", "ArrowRight": "→", "Meta": "⌘", "Control": "Ctrl", "Shift": "⇧", "Alt": "⌥", "Space": "Space"}


def key_label(key: str) -> str:
    return " + ".join(KEY_NAMES.get(part, part) for part in str(key).split("+"))


def keycap_png(frame: tuple[int, int], key: str, scale: float, out: Path) -> None:
    """A key cap, bottom centre, for `press` steps."""
    fw, fh = frame
    im = Image.new("RGBA", frame, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font(int(22 * scale))
    text = key_label(key)
    tw = d.textlength(text, font=f)
    pad = 16 * scale
    w, h = tw + 2 * pad, 22 * scale * 1.3 + 2 * pad * 0.7
    x, y = (fw - w) / 2, fh - h - 60 * scale
    d.rounded_rectangle([x, y + 4 * scale, x + w, y + h + 4 * scale], radius=10 * scale, fill=(0, 0, 0, 90))
    d.rounded_rectangle([x, y, x + w, y + h], radius=10 * scale, fill=(248, 250, 252, 240), outline=(120, 128, 140, 255),
                        width=max(1, int(2 * scale)))
    d.text((x + pad, y + pad * 0.7), text, font=f, fill=(20, 24, 30, 255))
    im.save(out)


def verified_text(evidence: str) -> str:
    """'API /api/x/y: data.a ✓, data.b ✓' → 'Backend verified · 2 checks passed'."""
    n = (evidence or "").count("✓")
    return "Backend verified" + (f" · {n} check{'s' if n != 1 else ''} passed" if n else " · API responded")


def badge_png(frame: tuple[int, int], text: str, scale: float, out: Path) -> None:
    """A green pill, bottom centre, for passing `api` checks."""
    fw, fh = frame
    im = Image.new("RGBA", frame, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font(int(19 * scale))
    label = "✓  " + text
    tw = d.textlength(label, font=f)
    pad = 14 * scale
    w, h = tw + 2 * pad, 19 * scale * 1.35 + pad
    x, y = (fw - w) / 2, fh - h - 60 * scale
    d.rounded_rectangle([x, y, x + w, y + h], radius=h / 2, fill=(20, 83, 45, 235), outline=(34, 197, 94, 255),
                        width=max(1, int(2 * scale)))
    d.text((x + pad, y + pad / 2), label, font=f, fill=(236, 253, 243, 255))
    im.save(out)


def moments(section: dict[str, Any], meta: dict[str, Any] | None, frame: tuple[int, int], work: Path, tag: str,
            fps: int) -> list[tuple[Path, float, float]]:
    """Automatic overlays from the event log: key caps for `press`, badges for passing `api` checks."""
    out: list[tuple[Path, float, float]] = []
    if not meta:
        return out
    scale = frame[0] / meta["viewport"]["width"]
    for n, e in enumerate(meta["events"]):
        if e["kind"] == "press" and section.get("keys", True):
            png = work / f"{tag}_key{n}.png"
            keycap_png(frame, e.get("label") or "", scale, png)
            out.append((png, max(0.0, e["t"] - 0.1), e["t"] + 1.4))
        elif e["kind"] == "api" and e.get("evidence") and section.get("verified", True) and e["t"] > 0.5:
            png = work / f"{tag}_badge{n}.png"
            badge_png(frame, verified_text(e["evidence"]), scale, png)
            out.append((png, e["t"], e["t"] + 3.2))
    return out


def sfx_cues(section: dict[str, Any], meta: dict[str, Any] | None,
             camera: list[tuple[float, float, float, float]]) -> list[tuple[float, str]]:
    """(time, sound) pairs: clicks on clicks, a whoosh as each zoom starts, a chime when a toast is awaited."""
    cues: list[tuple[float, str]] = []
    if meta:
        for e in meta["events"]:
            if e["kind"] in ("click", "check", "uncheck", "select"):
                cues.append((e["end"] - 0.05, "click"))
            elif e["kind"] == "wait_for":
                cues.append((e["end"], "chime"))
    for (t0, z0, _, _), (_t1, z1, _, _) in zip(camera, camera[1:]):
        if z0 == 1.0 and z1 > 1.0:
            cues.append((t0, "whoosh"))
    for at, name in section.get("cues", []):          # explicit cues from video.yaml: [[seconds, "jingle_in"], ...]
        cues.append((float(at), str(name)))
    return cues


def overlays(section: dict[str, Any], meta: dict[str, Any] | None, frame: tuple[int, int], work: Path,
             tag: str, log: Any = print) -> list[tuple[Path, float, float]]:
    """(png, start, end) for the section's callouts and spotlights."""
    out = []
    factor = frame[0] / meta["viewport"]["width"] if meta else 1.0
    events = meta["events"] if meta else []
    for kind in ("spotlight", "callouts"):
        for n, spec in enumerate(section.get(kind) or []):
            r = resolve(spec, find_event(events, spec), factor)
            if not r:
                log(f"  {kind} {spec}: no matching event with a target box, skipped")
                continue
            t, box = r
            if not (0 <= box[0] + box[2] / 2 <= frame[0] and 0 <= box[1] + box[3] / 2 <= frame[1]):
                log(f"  {kind} {spec}: target was off-screen at that moment, skipped")
                continue
            png = work / f"{tag}_{kind}{n}.png"
            if kind == "callouts":
                callout_png(frame, box, str(spec.get("text", "")), factor, png)
            else:
                spotlight_png(frame, box, factor, png)
            start = max(0.0, t + float(spec.get("delay", 0.15)))
            out.append((png, start, start + max(2.5, float(spec.get("duration", 3.0)))))
    for n, ph in enumerate(section.get("phrases") or []):          # timed key-phrase chips: {at, text, duration, pos}
        png = work / f"{tag}_phrase{n}.png"
        phrase_png(frame, str(ph["text"]), frame[0] / (meta["viewport"]["width"] if meta else 1440), png, str(ph.get("pos", "top-left")))
        start = float(ph["at"])
        out.append((png, start, start + max(2.0, float(ph.get("duration", 2.8)))))
    return out
