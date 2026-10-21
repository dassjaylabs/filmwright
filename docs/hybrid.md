# Hybrid films ("both")

Animated scenes and real recordings of your product in one narrated film: a title scene, a statement, a recording
of the feature in a clean window frame with an optional zoom, a few steps, a number, and the outro. One narration
track runs across the whole film, the score changes section on every segment change, captions are small and
burned in, and the result is delivered in 4K and HD.

```bash
python examples/both/make_sample_clip.py                         # a sample recording of a fictional app
python -m filmwright.hybrid.film examples/both/film.yaml tts
python -m filmwright.hybrid.film examples/both/film.yaml stills   # the animated layer (recordings show as black windows)
FPS=60 WORKERS=6 python -m filmwright.hybrid.film examples/both/film.yaml render
python -m filmwright.hybrid.film examples/both/film.yaml verify
```

With `mode: both` in `reel.yaml`, `filmwright build` runs the same steps. Recordings usually come from a demo run:
the `videos/<scenario>.mp4` files that the scenario runner writes ([demo.md](demo.md)).

## film.yaml

```yaml
title: Acme Tasks in one minute
file_prefix: acme-tasks-tour          # output names: acme-tasks-tour-4k.mp4, -hd.mp4, .srt
wordmark: ACME TASKS
tagline: Plan less. Do more.
url: acme-tasks.example
brand: {colors: {bg: "#0f1222", accent: "#7c5cff", alt: "#22c55e", warm: "#ff8a4c", ink: "#f4f5fb"}}   # or a brand folder
voice: {type: preset, speaker: ryan}
music: {mood: upbeat}
talking_head: {enabled: false, character: leo, corner: bottom-right}
captions: {burn_in: true}
outputs: [4k, hd]

segments:
  - {scene: title, headline: Meet Acme Tasks, sub: Plan less. Do more., say: "..."}
  - {scene: statement, text: "Requests arrive everywhere.\nNow they land in one place.", say: "..."}
  - clip: recordings/inbox.mp4
    trim: [0.5, 7.5]
    label: acme-tasks.example/inbox
    zoom: {at: 1.2, scale: 1.45, x: 0.35, y: 0.25, hold: 2.4}
    say: "..."
  - {scene: steps, title: How a rota gets made, items: [..., ..., ...], say: "..."}
  - {scene: stat, value: 11, suffix: " h", label: saved every week, say: "..."}
  - {scene: outro, cta: Try it free, say: "..."}
```

Every segment may have `say` (its narration; segments without it are silent) and `seconds` (a minimum length).

| segment | fields | on screen |
|---|---|---|
| `scene: title` | `headline`, `sub` | the logo draws itself, the headline builds word by word |
| `scene: statement` | `text` (`\n` for a second line, drawn in the accent colour), `sub`, `highlight: false` | big kinetic type |
| `scene: steps` | `title`, `items` (up to 5) | numbered cards fly in on the beat |
| `scene: stat` | `value`, `prefix`, `suffix`, `label` | a number counts up |
| `scene: headline` | `text` (`\n` for a new line; wrap words in `*stars*` to mark them in the accent colour), `sub`, `size` | kinetic type: words arrive in the rhythm of the line, with a slow push-in |
| `scene: chart` | `data: [{label, value}, ...]` (up to 8), `type: bar` or `line`, `title`, `sub`, `unit`, `prefix`, `highlight` (index or label; default the last), `note` | the chart builds up with values counting, the highlighted bar or point glows, `note` pops up as a callout |
| `scene: device` | `device: both`, `laptop` or `phone`; `image` (laptop screen) and `phone_image`: screenshots next to `film.yaml`; `title`, `sub` | a laptop and/or phone with depth and a glass sheen, showing your screenshots, or a generated dashboard in the brand colours |
| `scene: ui` | `title`, `sub`, `app`, `nav`, `rows` (up to 5), `placeholder`, `button`, `steps` | a product screen and a cursor acting out `steps`: `{click: input}`, `{type: "..."}`, `{click: button}` (adds the typed row), `{check: 1}` (ticks a row), `{toast: "..."}` |
| `scene: outro` | `tagline`, `cta` (defaults to the brand `url`) | logo, wordmark, tagline, call-to-action pill |
| `clip: <path>` | `trim: [from, to]` or `start`, `label` (shown in the window bar), `zoom`, `fit: clip` | the recording in a window frame |

A clip segment lasts as long as its narration (or `seconds`); if the recording is shorter, its last frame holds,
and with `fit: clip` the segment is stretched to show the whole recording. The recording's own sound is dropped.

`zoom` eases in to `scale` at `at` seconds into the segment, holds for `hold` seconds and eases back out over
`ramp` seconds (default 0.6); `x` and `y` (0 to 1) choose which part of the frame stays in view (0.5, 0.5 is the
centre).

Paths are relative to `film.yaml`. Scene starts snap to the music's beat, and each scene stays on screen long
enough for its animation (title 3.2 s, headline 2.8 s, steps 3.6 s, chart 4 s, device 3.6 s, ui 5 s, outro 4.2 s).
The README sample ([`docs/media/sample/film.yaml`](media/sample/film.yaml)) uses headline, chart, device and ui.
