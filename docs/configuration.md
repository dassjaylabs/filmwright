# reel.yaml reference

`filmwright new` writes this file for you. Every key is optional except `mode`; anything left out takes the
default shown. `filmwright options` prints the same choices.

| Key | Values | Default | What it does |
|---|---|---|---|
| `mode` | `demo`, `explainer`, `both` | `demo` | Screen-recorded walkthrough, fully animated explainer, or both in one film |
| `title` | text | `""` | The film's title (cards, file metadata) |
| `brand` | bundled name or folder | `example` | Colours, logo and wordmark ([brands.md](brands.md)) |
| `voice.type` | `preset`, `library`, `described`, `clone`, `system` | `preset` | Who narrates ([voice.md](voice.md)) |
| `voice.speaker` | `ryan`, `aiden`, … | `ryan` | Preset speaker |
| `voice.name` | `nora`, `james`, `olivia`, `henry`, `priya`, `marcus`, `ethan`, `graham`, `claire` | — | Library narrator ([voice.md](voice.md#library-voices)) |
| `voice.description` | text | | Described voice, e.g. "Calm, friendly narrator in her thirties" |
| `voice.sample` | path | | Cloned voice: the speaker's recording (needs a consent record) |
| `voice.style` | text | natural, relaxed | Delivery instruction for preset voices |
| `talking_head.enabled` | `true`, `false` | `false` | Animated, lip-synced presenter in a corner ([presenter.md](presenter.md)) |
| `talking_head.character` | `leo`, `leo-light`, `leo-stubble`, `sam`, `ana`, `lee`, `maya`, `raj`, `kit`, `jo` | `leo` | Which presenter |
| `talking_head.corner` | `bottom-right`, `bottom-left` | `bottom-right` | Where the presenter stands |
| `music.mood` | `upbeat`, `calm`, `corporate`, `inspiring`, `playful`, `epic`, `sad`, `suspense`, `none` | `upbeat` | Original score for the film ([music.md](music.md)) |
| `music.sync_to_scenes` | `true`, `false` | `true` | Land a downbeat on every scene change |
| `music.level` | dB | auto | Music level under the narration, before ducking (auto: -20 for a score, -26 for an ambient bed; e.g. `-16` is louder, `-24` quieter) |
| `sound_effects` | `subtle`, `full`, `off` | `subtle` | `subtle`: quiet interface sounds only (click, pop, tick, chime). `full` adds whooshes, swishes, risers and impacts on transitions. `off`: none |
| `captions.burn_in` | `true`, `false` | `true` | Small captions at the bottom of the frame. An `.srt` is always written |
| `outputs` | list of `4k`, `hd`, `vertical`, `square`, `web`, `gif`, `stems` | `[4k, hd]` | Files to deliver; `stems` comes with at least one video ([below](#stems)) |
| `disclosure` | `none`, `metadata`, `end-card` | `metadata` | Say that the narration voice is synthetic ([disclosure.md](disclosure.md)) |
| `checks.tool_names` | `off`, `warn`, `block` | `warn` | Flag film text that names production tools or leaves placeholders |
| `demo.scenarios`, `demo.video` | paths | `scenarios.yaml`, `video.yaml` | Demo inputs ([demo.md](demo.md)) |
| `explainer.format` | `story`, `montage` | `story` | Explainer format ([explainer.md](explainer.md)) |
| `explainer.project` | folder | `explainer` | Explainer project folder (`project.json`, `stories.json`) |
| `both.film` | path | `film.yaml` | The mixed film's segments ([hybrid.md](hybrid.md)) |

## Stems

`stems` adds the soundtrack's parts beside each film, for mixing or grading in an editor such as Kdenlive, Shotcut,
DaVinci Resolve or Audacity:

| File | What's in it |
|---|---|
| `<film>-narration.wav` | the narration alone |
| `<film>-music.wav` | the score, at its level in the mix and with the same ducking under the voice |
| `<film>-sfx.wav` | the sound effects (only when the film has any) |

They are 48 kHz stereo, 32-bit float WAV (float, so nothing clips), start at 0:00 and run with the film. Put them
on three tracks at the start of the timeline at 0 dB and they add up to the film's soundtrack (within the AAC
compression of the MP4). An end card from `disclosure: end-card` comes after the stems end. There is no timeline
interchange file (OTIO, EDL, FCPXML) yet.

```yaml
outputs: [hd, stems]
```

## Platform support

| Option | macOS (Apple Silicon) | macOS (Intel), Linux |
|---|---|---|
| Demo, explainer, both | yes | yes |
| `voice.type: preset`, `library`, `described`, `clone` | yes (one-time model download) | not yet: `preset`, `library` and `described` fall back to `system`; `clone` stops with an error |
| `voice.type: system` | yes | yes |
| Talking head, music, all outputs | yes | yes |

## Examples

A demo walkthrough with a presenter and calm music:

```yaml
mode: demo
title: Acme Tasks: recurring tasks
voice: {type: preset, speaker: aiden}
talking_head: {enabled: true, character: ana}
music: {mood: calm}
outputs: [4k, hd, vertical]
```

A batch of animated story explainers with an inspiring score, no presenter:

```yaml
mode: explainer
explainer: {format: story, project: explainer}
voice: {type: described, description: "Warm, unhurried narrator with a gentle British accent"}
music: {mood: inspiring}
outputs: [4k, hd, square]
```

Your own voice, cloned with consent:

```yaml
mode: both
voice: {type: clone, sample: voice/sample.wav}
disclosure: end-card
```
