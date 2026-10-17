---
name: filmwright
description: >-
  Make a narrated product film with the filmwright command: a screen-recorded demo walkthrough of a web app
  (real browser, zooms on each action), a fully animated explainer (characters, whiteboard sketches, motion
  graphics; one-use-case stories or a one-minute feature montage), or both in one film. Options: preset,
  described or cloned narration voice (cloning only with the speaker's recorded consent), an animated
  lip-synced talking-head presenter, original music in a chosen mood (upbeat, calm, corporate, inspiring,
  playful, epic, sad, suspense), burned-in captions, and 4K / HD / 9:16 / 1:1 / web / GIF outputs. Use it when
  someone asks for a demo video, product walkthrough, feature video, animated explainer, social clip, or a
  voice-over for a recording.
---

# filmwright

filmwright runs locally and is driven by one file, `reel.yaml`. Your job is the judgement: what the film should
show, what the narration says, and checking the result. The command does the deterministic work.

## 0. Check the machine

```bash
filmwright doctor            # what is installed and what this machine can run
filmwright setup             # ffmpeg, Chromium, espeak-ng, Rhubarb (prints any admin command for the person to run)
```

If `filmwright` is not installed: `pip install "git+https://github.com/dassjaylabs/filmwright"` (or
`pip install -e .` in a clone). Neural voices
(preset, described, cloned) need Apple Silicon and `filmwright setup --voice preset` (a multi-GB one-time
download: ask before starting it). Everywhere else the system voice works without a download.

## 1. Agree the options with the person

Ask only what they haven't said. Recommend defaults rather than listing everything.

| Choice | Options | Default |
|---|---|---|
| Film type | `demo` (record their app), `explainer` (animated, `story` or `montage`), `both` | from the request |
| Voice | `preset` (speaker `ryan`), `described` (a voice described in words), `clone`, `system` | `preset` |
| Talking head | yes / no, character `leo` `sam` `ana` `lee` `maya` `raj` `kit` `jo` | no |
| Music | `upbeat` `calm` `corporate` `inspiring` `playful` `epic` `sad` `suspense` `none` | `upbeat` |
| Outputs | `4k` `hd` `vertical` `square` `web` `gif` `stems` (separate narration/music/SFX WAVs) | `4k, hd` |
| Disclosure | `metadata`, `end-card`, `none` | `metadata` |

Then write the project non-interactively:

```bash
filmwright new <dir> --mode explainer --format story --voice preset --talking-head no --music inspiring \
  --outputs 4k,hd,square --yes
```

## 2. Fill in the content

- **demo:** `scenarios.yaml` lists what to do in the browser (docs/scenario-dsl.md). Derive scenarios from the
  feature (happy path, edge cases, a control), use role/label selectors, and point only at test environments
  (localhost, dev, staging) listed in `allow_hosts`. If the app needs sign-in, the person signs in themselves
  (`python -m filmwright.demo.login`); never type credentials and never print or commit `auth.json`.
  `video.yaml` holds one narrated section per recorded clip: write the narration from what the recordings show.
- **explainer:** edit `explainer/project.json` (product, wordmark, tagline) and `stories.json` (one story per
  film: character, problem, the product moment, outcome). See docs/story-config.md. Vary story shapes,
  palettes and characters across a batch.
- **both:** `film.yaml` is an ordered list of animated scenes and recorded clips, each with its narration
  (docs/hybrid.md).

Write for the ear: short sentences, numbers as spoken, no symbols. Only claim what the product really does, and
label sample data as sample data. Don't use real people, brands or logos other than the person's own.

## 3. Voice cloning (only when asked)

Clone a voice only when the person asks for their own voice, or a voice whose owner has agreed. The speaker
records the sample and confirms the consent statement themselves:

```bash
filmwright voice clone passage
filmwright voice clone record --speaker "<full name>"
filmwright voice clone preview --play
```

Never create a consent record on someone's behalf, and never try to work around the consent check.

## 4. Build and check

```bash
filmwright storyboard <dir>            # one panel per scene (still, line, timing) as HTML + PDF, for sign-off first
filmwright build <dir>                 # demo: records, then narrates; --skip-record reuses recordings
```

Run long builds in the background. Then look before handing over:
- the demo results table (`results.md`): report failures honestly; a product bug is a finding;
- two or three stills (`ffmpeg -ss <t> -i <file> -frames:v 1 still.png`) for text fit and layout;
- listen to the first section; rephrase any sentence the build flags as unclear.

Deliverables are in `<dir>/out/final/` (listed in `manifest.json`). Report each file's length and any check that
needed attention.
