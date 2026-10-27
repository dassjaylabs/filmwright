# Directing the film

Read this before writing `video.yaml`. The runner records sharp, real-time clips and logs where every step
happened (`videos/<id>.events.json`). You decide what the viewer should look at, and when, the way an
editor cuts a product demo.

## Contents
- Recording settings (scenarios.yaml)
- Film settings (video.yaml)
- Effects: focus, callouts, spotlight
- Explainer scenes
- The presenter
- Automatic touches: badges, key caps, sound effects, transitions, chapters, teaser
- Redaction
- Music
- How to decide: a director's checklist

## Recording settings (scenarios.yaml)

```yaml
recording:
  resolution: 4k        # 4k | 1440p | 1080p | 720p. 4k captures at 3× pixel density (4320×2430 from a 1440×810 viewport)
  fps: 30
  pace: 0.8             # seconds of stillness after every visible action, so viewers can follow
  cursor: true          # a visible pointer that glides to each target before acting
  ripple: true                             # a ring on every click and a press-scale on the pointer (default: on with the cursor)
  glide_ms: 650
  typing_delay_ms: 70   # `type` steps, and `fill` steps up to 60 characters, are typed key by key
  engine: hq            # hq (default) | playwright (Playwright's built-in recorder: soft video, use only if hq fails)
```

On a machine short of memory, or for a quick draft, use `resolution: 1080p`, which captures at 2×.

Each scenario also takes `hold:` (seconds to rest at the end, default 2). For a calmer film, raise `pace`
(1.0–1.2) rather than adding `pause` steps everywhere. Put explicit `pause` steps where the viewer has to read
something: a banner, a dialog's text, a result.

`events.json` lists, for every step:
- `step` (its number);
- `kind`;
- `label` (the target, e.g. `button "Save"`);
- `t` and `end` (seconds into the clip);
- `box` (CSS px, from the 1440×810 viewport).

Read it to pick moments and anchors; don't guess times.

## Film settings (video.yaml)

| Field | Default | Notes |
|---|---|---|
| `resolution` | from the clips (4K for a 3× capture) | or `size: {width, height}` |
| `voice` | preset voice (`ryan`) | same fields as reel.yaml; see docs/voice.md |
| `music` | none | `{mood: upbeat, sync_to_scenes: true}`; see Music |
| `checks` | `{tool_names: warn}` | optional lint of the film's text (off, warn, block) |
| `sections[].clip` / `explainer` | — | a recording, or an HTML scene to record |
| `sections[].label` / `label_seconds` | — / 4 | the lower-third shown at the start |
| `sections[].focus` / `callouts` / `spotlight` | — | the effects below |
| `sections[].fit` | `hold` (video), `stretch` (GIF) | what happens when narration outlasts the clip |

## Effects

Every effect is anchored to an event in the clip:
- `target:` matches an event's label, case-insensitively and by substring. Add `nth: 1` for the second match.
- `step:` is the step number.
- `box: [x, y, w, h]` (CSS px) needs an explicit `at:` (seconds into the clip).

An effect starts when its event happened; `at:` overrides that.

**focus**: zoom in on a target, hold, zoom out.

```yaml
focus:
  - {target: 'button "Save"', hold: 2.5}            # zoom fitted to the target, eased in and out
  - {step: 6, zoom: 1.6, hold: 3}                   # explicit zoom level
```

- **Hold:** at least 2 s, whatever you write (default 2.5). The ease in and the ease out take 0.7 s each.
- **Zoom level:** fitted to the target, up to 1.8×, so a wide banner gets less. A target that fills most of
  the screen is skipped with a note; use a spotlight for it instead.
- **Back-to-back zooms:** they pan from one target to the next without zooming out in between.

**callouts**: an accent outline around the target and a short dark label beside it.

```yaml
callouts:
  - {target: "status-banner", text: "Appears only when the record changed", duration: 3}
```

**spotlight**: dim everything except the target.

```yaml
spotlight:
  - {target: 'dialog "Confirm changes"', duration: 3}
```

Callouts and spotlights last at least 2.5 s and fade in and out. They're drawn before the zoom, so they zoom
with the picture.

## Explainer scenes

Use an explainer when the narration explains something the app doesn't show: a rule (why two copies
exist), a flow (what happens after Approve), or a before/after. Copy `templates/demo/explainer.html` (inside the
installed package, `src/filmwright/templates/demo/`) to `<run-dir>/explainers/<name>.html` and edit its `SCENE`: an eyebrow, a one-line idea, an optional sentence,
and three to five steps (`key: true` marks the one to emphasise).

```yaml
- explainer: explainers/<idea>.html
  label: "How it works"
  text: <One or two sentences about the idea the scene shows.>
```

It's recorded at the film's resolution for exactly as long as the narration runs. The steps arrive evenly,
and the scene rests for the last two seconds. You can write your own HTML/CSS animation instead; keep it to
1440×810 CSS px and read `?d=<seconds>` to pace it. Use at most one or two explainers per film; they're
seasoning.

## The presenter

A rigged 2D cartoon narrator in a bottom corner, mouth synced to the narration with Rhubarb Lip Sync
(loudness-driven where Rhubarb isn't available). It's a proper character rig, not a sticker:
- two-bone arms with inverse kinematics, drawn in front of the body, with pointing, open-palm, relaxed and
  thumbs-up hands;
- it **aims at the real target**: each zoom's coordinates are mapped into the character's space, so the
  finger, eyes, head turn and body lean all face the thing the camera is about to show, a second before it
  zooms; then it steps aside (fades out) while the camera is in;
- an open-palm "present" when a section opens on a new screen, a wave on the first section, a thumbs-up and
  nod on the last;
- it never hides what matters: for each section it picks the bottom corner with less going on (the label
  moves to the other corner), and steps aside (fades out) for any remaining step whose target sits under it,
  as it does for zooms; `auto_side: false` pins the corner;
- the finger bends at the wrist to line up with the exact target, arriving a beat after the arm; the eyes move
  first and linger after; a blink on every gaze shift; a small shrug toward the target;
- idle poses (hands clasped, hand on chin, hand on hip, at rest) that it drifts between every 7–12 s during
  long sections, never mid-gesture; a glance at the camera as each section opens and when the narration ends;
- animation principles underneath: anticipation, ease-out with a little overshoot, settle, eased release;
  breathing, weight shift, blinks (some double), and micro-nods on syllable beats; mouth shapes cross-fade
  and move the jaw;
- tapered limbs (a short sleeve, a skin forearm, a visible elbow that always bends the natural way) on a padded
  canvas, so hands and fingers are never clipped.

```yaml
presenter: {style: leo, height: 0.25}                # the default host (see below)
presenter: {style: {preset: leo, shirt: "#7c5cff", shirt2: "#5b3fd9"}, position: bottom-right, height: 0.25}   # a brand-coloured tee
presenter: {style: lee, position: bottom-left, height: 0.21}                                                   # another character
```

**The default host is `leo`**, drawn in `assets/presenter/presenter.html` (set `FILMWRIGHT_PRESENTER_HTML` to try another
character file): a short men's cut with a side part, a blue crew tee, shaded skin, hair sheen, a cool edge light so the host stands
out on a dark page, outlined hands with parametric fingers, and a ribbed collar. Variants: `leo-light` (lighter skin) and
`leo-stubble`. The animation vocabulary, all deterministic and driven by the timeline: point (arm held inside a natural reach cone;
the eyes and head carry targets beyond it), present, wave, thumbs-up, emphasis **beats** on stressed words, **counting** 1 to 5 on
the fingers ("three steps"), a **shrug** ("not a guarantee"), **hands together** while listening, mood (smile and brows),
loudness-driven bob and brow flashes, eye darts and blinks, slides in and out. The pipeline sends those from the narration's word
times (`filmwright.demo.cues`). See docs/presenter.md for using the host over any film.

| Preset | Look | Temperament |
|---|---|---|
| `leo` (default) | short dark quiffed hair, blue tee, no accessories | friendly, steady (0.9) |
| `sam` | brown hair, green tee, headphones | friendly, steady (energy 1.0) |
| `ana` | long dark hair, blue tee, earrings | warm, calm (0.8) |
| `lee` | side part, glasses, purple tee, headphones | thoughtful, precise (0.9) |
| `maya` | curly hair, coral tee, earrings | upbeat, expressive (1.25) |
| `raj` | side part, short beard, teal tee | confident, composed (0.9) |
| `kit` | ginger bun, freckles, mustard tee, headphones | playful, quick (1.3) |
| `jo` | grey hair, glasses, navy tee | calm mentor (0.7) |

`energy` scales how much the character moves at idle, while talking and in gesture snap. Any field
(`skin`, `hair`, `shirt`, `hairStyle: short|long|curly|bun|part`, `glasses`, `beard`, `freckles`,
`earrings`, `headphones`, `energy`) can be overridden on a preset.

Per section, `presenter: false` hides it (e.g. a dense dashboard). The build renders presenter sections in
parallel at 30 fps; expect it to add a few minutes to a 4-minute film. Preview a style over a real frame,
with crosshairs at the aimed targets, with
`python -m filmwright.presenter preview --style leo --bg frame.png --out pv.mp4`, and the idle poses with `--idle-demo`.

## Automatic touches

These come from the runner's event log and need no configuration; turn any off per section.

| Touch | What | Off switch |
|---|---|---|
| **Verified badge** | a green pill, "Backend verified · 2 checks passed", for 3 s at every passing `api` step | `verified: false` |
| **Key caps** | "Esc", "Enter ⏎" bottom-centre at every `press` step | `keys: false` |
| **Sound effects** | a soft click on clicks and a chime when a `wait_for` (usually a toast) completes; synthesised, about 25 dB under the voice. With `sound_effects: full` in reel.yaml (or `sfx: {sounds: full}`), also a whoosh as each zoom starts and a swish between sections | `sfx: false` (film or section), `sfx: {level: 0.3}` |
| **Transitions** | `transition: {type: smoothleft, duration: 0.6}`; any ffmpeg `xfade` type: `dissolve`, `wipeleft`, `slideleft`, `circleopen`, … Default `cut` (with fades to black) | `transition: {type: cut}` |
| **Chapters** | one per section label, visible in players that show chapters | — |
| **Poster + teaser** | `<name>-poster.png` and a 10 s `<name>-teaser.gif` from the first zoom moment, for chat and pull requests | `poster: false`, `teaser: false`, `teaser: {seconds: 8, width: 480}` |

Badges and key caps share the bottom-centre band, so they never collide with the label (bottom-left) or the
presenter (bottom-right).

## Redaction

Blur anything that shouldn't be in a shared video, while recording:

```yaml
recording:
  redact: ["[data-testid=contact-email]", ".phone", "td.revenue"]
```

The selectors get `filter: blur(9px)` in every page the scenarios visit. Check a still afterwards: redaction is
only as good as the selectors.

## Music

```yaml
music: {mood: upbeat}                          # an original score composed for the film, a downbeat on every section start
music: {mood: calm, sync_to_scenes: false}     # a very quiet ambient bed instead of a score
music: {mood: none}                            # no music
music: {file: music/bed.mp3}                   # your own royalty-free track (looped and faded to fit)
```

Moods: `upbeat`, `calm`, `corporate`, `inspiring`, `playful`, `epic`, `sad`, `suspense` (docs/music.md). The music is
synthesised on your machine: no samples, no model, nothing to license.

`level` is how far under the narration it sits, in dB (default -20 for a score and -26 for an ambient bed, so `level: -24` is a little quieter than the score default); `level_lufs`
sets the absolute loudness instead. It ducks further while someone speaks (`duck: false` turns that off). The
narration-only `-voiceover.m4a` never has music in it.

## How to decide: a director's checklist

Go section by section, with the clip's `events.json` and your narration open:

1. **What is this section's one moment?** Usually it's the thing the narration names: a banner appearing,
   a chip, a confirmation. Zoom on it, and time the zoom to the event, not to when the narration mentions it.
2. **Is the target small?** Buttons, chips and a line of text get a `focus`. Panels and dialogs get a
   `spotlight`, or nothing.
3. **Does the viewer need a word of help?** If the meaning isn't obvious from the UI text, add one `callout`
   of five to eight words. Don't repeat what the narration already says.
4. **Is the idea invisible?** Then add an explainer before the section that needs it.
5. **One effect at a time.** Don't stack a zoom, a callout and a spotlight on the same moment. Allow
   at most two or three effects per section.
6. **Leave room.** Hold every zoom at least 2 s, and give the viewer a second at full frame between
   effects. If the narration is longer than the clip, the last frame holds; don't put a zoom on that frame.
7. **Typing and navigation:** don't zoom while the page navigates. A zoom on a field while it's being typed
   into is fine when the typed value matters.
8. **Check stills** at each effect's midpoint (`ffmpeg -ss <t> -i film.mp4 -frames:v 1 still.png`): the
   target is fully in frame, readable, and not covered by the section label.

## Auto-focus: zoom in where the action happens

Every recorded clip gets `auto_focus: true` by default (in a series built with `filmwright.series.mkepisode` too): the camera picks the clip's real
actions (clicks, hovers, typing, ticks, tab switches), eases in on each one, holds about 2.6 s, and eases back out.
A navigating click zooms in just before it fires and out as it does. A wide card (too big to zoom on) is framed by
its upper-left part, where the headline is. The host fades out of the way during every zoom. A target below the fold is
scrolled into view before its step, and the recording rests there for 1.2 s, so the zoom eases in over the page as
it is when the action happens.

Per section: `auto_focus: false` (none), `"add"` (automatic plus your own `focus:` entries), `auto_focus_max` (default 3),
`auto_focus_zoom` (max, default 1.9), `auto_focus_hold`, `auto_focus_skip: [step numbers]`. For a moment the events do
not cover (a table that has just scrolled into view) add an explicit region:
`focus: [{box: [x, y, w, h], at: <seconds into the clip>, zoom: 1.4, hold: 3.4}]` (box in CSS px).

Why a zoom can silently not happen: `focus: [{target: ...}]` on a target that already fills most of the screen is
skipped ("zoom skipped (use a spotlight)"). Check the build log for "camera: N zoom(s)"; 0 means no zoom was made.

## Checks on the film's text

`checks: {tool_names: warn}` (the default) runs a short lint over `video.yaml`, the subtitles and the finished files'
metadata, and prints anything that names a production tool or still holds a `<placeholder>`. `block` stops the build
instead; `off` skips it. The files themselves are always written clean: no encoder tags and no encoder-settings data.
Whether and how the film says that its voice is synthetic is a separate setting: `disclosure` in reel.yaml (docs/disclosure.md).
