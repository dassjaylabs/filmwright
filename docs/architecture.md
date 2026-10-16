# Architecture

filmwright is one Python package with one command (`filmwright`). A project is a folder with a `reel.yaml`
that picks the film type and the options; the mode-specific inputs sit next to it.

```
src/filmwright/
  cli.py  wizard.py  config.py  paths.py      the command, the interactive wizard, reel.yaml loading
  core/
    voice/      narration: preset, described and cloned voices, espeak-ng fallback, read-back check
    music/      original score composed per mood, synced to scene changes; quiet ambient beds
    export/     4K / HD masters, 9:16 and 1:1 social cuts, web renditions, GIF teaser, posters
    sfx.py      synthesised clicks, whooshes, risers, impacts
    textcheck.py   optional lint for film text (tool names, placeholders)
    disclosure.py  synthetic-voice disclosure: none | metadata | end-card
    mix.py      loudness-normalised narration + music + effects mix
  demo/         screen-recorded walkthroughs: scenario runner, recorder, login, camera effects, film builder
  presenter/    the animated talking-head host (lip-synced), usable over any film
  explainer/    fully animated films: story films and the one-minute montage
  hybrid/       "both": animated scenes and recorded clips in one narrated film
  series/       numbered episodes, branded intro/outro scenes, batch builds, posting plan
  assets/       fonts (OFL), presenter characters, motion.js (the animation engine)
  templates/    scene, story, montage and example templates
  brands/example/  the fictional example brand
  tools/setup.sh   system dependency check / install
```

## reel.yaml

```yaml
mode: demo                 # demo | explainer | both
title: "Acme Tasks in two minutes"
brand: example             # bundled brand name or a path to a folder with brand.yaml

voice:
  type: preset             # preset | described | clone | system
  speaker: ryan            # preset: built-in speaker name
  description: ""          # described: "Calm, friendly narrator in her thirties"
  sample: voice/sample.wav # clone: a recording of the speaker (consent required, see docs/voice.md)
  style: "Natural, relaxed and conversational"
talking_head:
  enabled: false
  character: leo           # leo | sam | ana | lee | maya | raj | kit | jo
  corner: bottom-right
music:
  mood: upbeat             # upbeat | calm | corporate | inspiring | playful | epic | sad | suspense | none
  sync_to_scenes: true
  level: -20               # optional: dB under the narration (auto by default)
captions:
  burn_in: true            # small captions at the bottom; an .srt is always written
outputs: [4k, hd]          # 4k | hd | vertical | square | web | gif
disclosure: metadata       # none | metadata | end-card  (see docs/disclosure.md)
checks:
  tool_names: warn         # off | warn | block: flag film text that names production tools

demo:      {scenarios: scenarios.yaml, video: video.yaml}
explainer: {format: story, project: explainer/}     # story | montage
both:      {film: film.yaml}
```

`filmwright build` resolves this file into the inputs each pipeline already understands (`video.yaml` for
demo, `project.json` for explainer, `film.yaml` for both) under `.filmwright/`, runs the pipeline, then applies
exports and disclosure.

## Contracts between modules

- **Voice.** `filmwright.core.voice.make_voice(cfg: dict) -> Voice` where `Voice.say(text, out_wav) -> float`
  (seconds). `cfg` is the `voice:` block. `clone` refuses to run unless a consent record exists for the sample
  (`filmwright voice consent`). `system` uses espeak-ng and works everywhere.
- **Music.** `filmwright.core.music.score(out_wav, seconds, cuts, mood, bpm=None) -> Path`: an original
  track for the mood with a downbeat on every cut (scene change, seconds). `filmwright.core.music.ambient(out_wav,
  seconds, mood) -> Path`: a quiet bed. `MOODS` lists the moods.
- **Presenter.** `filmwright.presenter.overlay_on_video(in_mp4, narration_wav, out_mp4, character, corner)`
  draws the lip-synced host over any finished film.
- **Export.** `filmwright.core.export.render_outputs(master_mp4, srt, outputs, out_dir, stem) -> list[Path]`.
- **Disclosure.** `filmwright.core.disclosure.apply(mp4, mode, voice_type) -> Path`.
- **Animation.** Templates load `assets/motion.js` (MIT, part of this repo), a deterministic, seek-only
  timeline engine. Every page exposes `window.__seek(t)`, `window.__duration` and `window.__ready`, and frames
  are captured by seeking, so renders are identical every time.
