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
| `clip: <path>` | `trim: [from, to]` or `start`, `label` (shown in the window bar), one camera (`zoom`, `pan` or `cam`), `fit: clip` | the recording in a window frame |

A clip segment lasts as long as its narration (or `seconds`); if the recording is shorter, its last frame holds,
and with `fit: clip` the segment is stretched to show the whole recording. The recording's own sound is dropped.

`zoom` eases in to `scale` at `at` seconds into the segment, holds for `hold` seconds and eases back out over
`ramp` seconds (default 0.6); `x` and `y` (0 to 1) choose which part of the frame stays in view (0.5, 0.5 is the
centre).

## Cameras on a recording

A clip takes one of three cameras:

- **`zoom`**: one push in and back out, as above. Fine for a desktop viewer, where the whole window is readable.
- **`pan`**: the phone-readable close-up. The camera pushes in to `zoom` and visits each `stop` (an x, or `[x, y]`,
  fractions of the picture) in turn, holding on every stop for at least a second (`hold`, never less than 1.0)
  and taking about 1.1 s to move between them (`move`). `at` is when the push starts (`at: 0` starts pushed in,
  so the wide shot never shows); `out: true` eases back to wide at the end, otherwise the camera stays in.

  ```yaml
  - clip: recordings/list.mp4
    trim: [6.0, 13.5]
    pan: {zoom: 2.5, y: 0.17, stops: [0.22, 0.85], at: 0.5}     # the row's name side, then its amount side
    say: Who bought the most, their role, and the amount.
  ```

- **`cam`**: explicit keyframes `[second, zoom, x, y]`, eased (smoothstep) between them; values left out carry
  over from the previous row, so a hold is the same position at a later time. `pan` is just a `cam` written for you.

  ```yaml
  cam: [[0, 1], [0.6, 2.5, 0.22, 0.17], [1.8, 2.5], [3.0, 2.5, 0.85, 0.17], [4.0, 2.5], [4.8, 2.3, 0.30, 0.43], [5.9, 2.3]]
  ```

A camera path sets the segment's minimum length (its last keyframe), and a recording that ends before the path
does holds its last frame under the moving camera. A recording with the window's aspect is cropped and scaled
straight from its own pixels, so a 2.5x push from a 4K capture still looks sharp.

### Cuts for phones

On a phone, X, LinkedIn and the like show a 16:9 film about 390 px wide, and the square and vertical renditions
show the *same* 16:9 picture at the same width over a blurred background. So the frame shape cannot fix small
type: a web app's 13 px text at a 1.12x push is about 3 px tall on the phone. The camera can. For a cut meant to
be watched on a phone:

- hold the camera at **2.4 to 2.8x** on the thing the narration is describing, and show the wide shot only for a
  moment in and out (or not at all, `at: 0`);
- **pan across** a wide row rather than cropping it: name side, then amount side, each held for a full second;
- use `frame: wide` (the window 5% wider and higher up, clear of the captions) and `captions: {scale: 1.4}` in
  reel.yaml so the captions read too;
- post the **square** file to a feed (it takes the most feed height without being cropped) and keep the vertical
  file for full-screen placements.

Check the result on a phone-sized still: `ffmpeg -ss <t> -i film-hd.mp4 -frames:v 1 -vf scale=390:-1 phone.png`.

## Frame, pace and a review sheet

- `frame: default | wide | {x, y, w, h}` sets where the recording window sits on the 1920x1080 page.
- `holds: 0.75` scales every scene's minimum time on screen, for a brisker cut; `tempo: 1.1` speeds the narration
  by 10% (it is checked at normal speed first).
- `python -m filmwright.hybrid.film film.yaml sheet` writes `<prefix>-sheet.png`: two frames per segment with its
  kind, timing and narration, frame 1 marked as the thumbnail. Look at it before handing a film over.

Paths are relative to `film.yaml`. Scene starts snap to the music's beat, and each scene stays on screen long
enough for its animation (title 3.2 s, headline 2.8 s, steps 3.6 s, chart 4 s, device 3.6 s, ui 5 s, outro 4.2 s).
The README sample ([`docs/media/sample/film.yaml`](media/sample/film.yaml)) uses headline, chart, device and ui.
