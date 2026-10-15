# Branded series: animated scenes and numbered episodes

Use this to make a numbered series of short demo films for a product: an animated intro and outro in the brand's
colours, a feature explainer scene per episode, the talking-head host, zooms on the action, word-timed callouts,
sounds, burned-in captions for social, web-ready files and a posting plan. One film works the same way: a series of
one (`of: 1`).

## What you need

1. **A brand**: a folder with `brand.yaml` and `logo.png` (docs/brands.md). The bundled `example` brand ("Acme") is a
   good starting copy.
2. **A series folder** with `series.yaml` and one spec per episode (`specs/ep01-<slug>.yaml`, ...).
3. **An environment you may record**: a local or test build of your app, and, if it needs a sign-in, a saved session
   (docs/scenario-dsl.md, Sign-in).
4. **Your narration rules**, if your product has any: what the voice-over, cards and captions must never say or show.
   Point `narration_rules:` in brand.yaml at that file so whoever writes the scripts reads it first.

```yaml
# series.yaml
brand: my-brand            # a folder next to series.yaml, or a bundled brand name (example)
specs: specs
posts: posts
web: web
groups: [{name: "Season 1", episodes: [1, 6]}, {name: "Season 2", episodes: [7, 12]}]
notes: ["anything to check before posting"]
```

## An episode spec

```yaml
dir: runs/my-series/ep02-boards             # where this episode is recorded and built
slug: boards                                # folder and file names: letters, digits and dashes only
episode: 2
of: 12
title: [Shared, Boards]                     # two lines on the intro; the second may be ""
tagline: One line under the title.
next: Title of the next episode             # "" on the last one
theme: main                                 # an accent from brand.themes
cast: [manager, you]                        # who walks in during the intro, in the order the narration names them
tile: trend                                 # trend | flag
intro_text: Narration over the intro.
outro_text: Narration over the outro.
voice: {type: preset, speaker: ryan}        # optional: overrides the brand's voice (docs/voice.md)
music: {mood: upbeat}                       # optional: overrides the brand's music (docs/music.md)
explainers:                                 # animated idea scenes between the intro and the recorded clips
  - {template: funnel, params: {title: "Narrowing it down"}, text: "narration for the scene", label: "The idea"}
scenarios: [...]                            # scenario steps, see docs/scenario-dsl.md
sections:                                   # one per recorded clip, in viewing order
  - {clip: S01, label: "1 · The board", text: "narration written from what the recording shows"}
caption: Social post text.
hashtags: ["#..."]
```

```bash
python -m filmwright.series.mkepisode gen    specs/ep01-*.yaml   # scenes + scenarios.yaml + video.yaml
python -m filmwright.series.mkepisode record specs/ep01-*.yaml   # then look at frames: signed in? right data?
python -m filmwright.series.mkepisode build  specs/ep01-*.yaml   # narrate and assemble the 4K master
python -m filmwright.series.mkepisode social specs/ep01-*.yaml   # 1080p cut with small burned-in captions + post text
python -m filmwright.series.series_build <series> --episodes 2-12   # unattended batch, progress in STATUS.txt
python -m filmwright.core.export.web <series>                     # 720p/480p MP4, posters, WebVTT, preview page
```

Make episode 1 first and judge it before running the batch.

## Feature explainer scenes

Templates live in `src/filmwright/templates/brand-scenes/scenes/`. Every default is sample content you replace with
`params`:

| Template | Idea it shows | Params |
|---|---|---|
| `merge-streams` | several sources merge into one stream | `labels[3], result, title, caption` |
| `bars-shift` | up/down bars that move between two periods | `title, fromLabel, toLabel, unit, rows[{label,a,b}]` |
| `rank` | jumbled bars re-sort into a ranking | `title, unit, rows[{label,value}]` |
| `funnel` | a big list narrowed by filters to a short one | `title, topLabel, filters[], bottomLabel, keep` |
| `balance` | two options weighed against each other | `title, left, right, sourceLabel, showCharacter` |
| `flow` | items flowing from a source to targets | `source, targets[{label,value}], unit, title` |
| `calendar` | dates lighting up with a counter | `month, year, firstWeekday, days, highlights[{day,count}], title, countLabel` |
| `timeline` | different kinds of events building a trail | `tag, events[{kind: person/star/work/announce, label}], title` |
| `stack` | a pile of papers condensing into one summary | `title, stackLabel, resultLabel, bullets[3]` |

Each scene runs 10 to 14 seconds and counts numbers up where it shows them. Use generic labels (no real people or
companies), nobody drawn as a villain, and sample data that is clearly sample data.

### Writing a scene

Every scene is a **pure function of time**: `render(t)` sets all styles for second `t`. No CSS animations or
transitions, no `setTimeout`, no `performance.now`, no `Math.random` (use `Scene.rnd(seed)`). The recorder sees
`window.__seek` and captures the scene frame by frame, so every take is identical whatever the machine is doing.

`runtime.js` gives a scene `Scene.define({setup, render})`, the viewport (`W`, `H`, `U`, `vertical`), easing
(`ease.out/io/back`), `seg(t, start, dur)`, `lerp`, `rnd(seed)`, `el()/svg()` helpers, `field()` (the drifting dot
background), `strip()` (the series dots), `countUp()` and `Scene.accent`. `window.PARAMS` carries the scene's
parameters; mkepisode injects them between `/*PARAMS*/` and `/*END*/`. Scenes work in landscape (1440x810) and
vertical (430x764): use `W`, `H`, `U` and `vertical`, never fixed pixel coordinates. Preview a scene by opening it in
a browser (live clock), or in Playwright with `?capture=1&d=11` and `page.evaluate("t => window.__seek(t)", 6)`.

### Characters

`characters.js` is a flat cartoon rig: blinking eyes that look where you tell them, a surprised face, brows, an
arm-swinging walk, a squash-and-stretch landing, a wave, and props that activate (`use` 0 to 1): `manager` (tie),
`lead` (lapel pin), `consultant` (briefcase), `you` (magnifying glass), `builder` (hard hat), `marketer` (megaphone),
`reviewer` (badge), `host` (hand bell), `analyst` (clipboard), `reader` (open book). Set the intro cast per episode
with `cast:`; use `{look: builder, name: "Dev team"}` for your own label.

### Colours

The scenes are drawn in the example brand's palette. For another brand, mkepisode recolours every scene by role
(`templates/brand-scenes/palette.json` lists which tones are neutrals and which are accents): neutrals follow the
brand's background ramp, accents take the brand accent, and the semantic colours (green up, red down, category
colours) stay. It also swaps in the brand's logo, wordmark and headline font and can tint the host's shirt.

## What you get by default

Each effect can be switched off per brand in `effects:` (docs/brands.md).

- **Frame-exact animated intro and outro** with the cast, "Episode N of M", a strip of dots and a "Next up" line.
- **A feature explainer scene** per episode, recoloured from the brand.
- **The host** at 25% of the frame height in the bottom-right corner: waves in the intro, points at what the camera
  shows, beats on stressed words, counts on its fingers, rests with hands together, gives a thumbs-up at the end, and
  steps aside during zooms. `host_outro: false` drops it from the outro.
- **Auto-focus zooms** on every real action in a recorded clip. Check the build log says `camera: N zoom(s)`.
- **Word-timed effects**: a callout, spotlight or key-phrase chip (`phrases: [{at, text, duration, pos}]`) can say
  `word: "export"` and appear when it is spoken. Use it only if the thing is already on screen at that moment;
  otherwise use `at: <seconds into the clip>`.
- A slow camera push, a click ripple and a smooth pointer, soft pops and swishes, music, chapters, a poster and a
  teaser GIF. Optional synthesised stings (`jingle_in`, `sparkle`, `jingle_out`) with `effects: {jingle: true}`.
- **Social cut**: 1080p, loudness-normalised, small captions at the bottom, clear of the host.
- **Clean files**: every exporter writes output with empty encoder tags and no encoder-settings data.

**Vertical (9:16):** set `vertical: true` in a spec. The site is recorded at 430x764 (its mobile layout), scenes use
their portrait layouts, the film is 1080x1920 and the host is smaller. Check each vertical recording by eye.

## Sessions

A recorded clip silently shows the logged-out view when the session has expired. So:

- With `auth.mode: chrome-session`, series_build copies the session from your signed-in Chrome tab before every
  episode (macOS; needs Chrome > View > Developer > Allow JavaScript from Apple Events). It reloads the tab when the
  token is about to expire and saves the session without printing it.
- `auth.account_check` makes series_build verify the right account before every recording and stop if it fails. Give
  every project one; it takes a single `api` GET.
- `auth.strip_keys` removes saved keys you don't want in the session file (an email, table state); `auth.token_key`
  names the key that holds the token.
- Sessions are personal data: `auth.json` stays in run folders, never committed or shared. Delete it when done.

## Lessons

- A hand-placed `focus` on a target that fills the screen is skipped. Auto-focus avoids this; check the log.
- A word anchor on something that appears later (after a scroll or navigation) outlines the wrong place.
- Tokens expire; a lapsed one produces plausible-looking guest clips. Verify before recording.
- Rebuilding does not need a new recording; only changes to scenarios or the app's data do.
- Recordings show the product on the day; names and numbers on screen change later. Don't narrate a specific figure.
