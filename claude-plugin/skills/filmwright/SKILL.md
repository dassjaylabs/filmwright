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

### Shape of a film that gets watched

- **Open on the viewer's own problem, in their words, inside the first 8 seconds.** Not "Meet Acme" but the
  situation they recognise ("You own five stocks. So do their insiders. Who's buying?"). Then the general
  problem (volume, format, time), then the pivot to the product, then the features, then one closing line that
  calls back to the opening. Keep the problem beats soft: a pause and a question, not alarm.
- **Frame 1 is the thumbnail.** Compose the opening frame fully at t = 0 (headline, illustration, chip), then
  let it come alive. A blank or half-built first frame is what the feed shows while muted.
- **Narration describes the kind of thing on screen, not the instance.** "Each row shows who bought, their role
  and how much", never the company, person or figure in the recording. The film stays true after the data moves
  on, and it never reads as a tip. The data on screen can be current; say "as of" in a corner, not aloud.
- **One film, every feature, under about two minutes** for a tour; 40 to 50 seconds for a single-feature clip.
  `holds: 0.75` and `tempo: 1.1` in film.yaml make a tour brisk without clipping any sentence.
- **Voice as a persona, not a setting.** Pick a narrator the audience would trust for the subject (a finance film:
  `library` voice `graham` or `claire`, or a `described` voice such as "British man in his early fifties, a
  veteran City fund analyst, deep, unhurried, dry"). Never the system voice for a published film. Keep one
  voice per film and alternate voices across a series.
- **Sound stays out of the way.** `sound_effects: subtle` (the default) and music well under the voice; many
  people find whooshes and risers tiring, and half the audience watches muted anyway, so captions are on.

### Cuts for phones

Most social viewers watch on a phone, where a 16:9 film is about 390 px wide and the square and vertical
renditions show the *same* picture at the same width. A screen recording of a web app at a gentle zoom is
unreadable there (13 px site text comes out about 3 px tall). For a phone cut (`both` films, docs/hybrid.md):

- give every recording a `pan` camera: 2.4 to 2.8x on the thing being described, stops on the name side and the
  amount side of a row, **a full second on each stop** and about 1.1 s per move (the defaults), the wide shot
  only for a moment if at all;
- don't repeat the same pan on every clip: teach "how a row reads" with a full pan twice at most, then vary
  the move to fit each feature (drift down a column, a static close-up on a control, start pushed in, end with a
  pull-out to wide), and alternate two zoom levels so the camera never feels like a loop;
- `frame: wide` in film.yaml and `captions: {scale: 1.4}` in reel.yaml;
- post the square file to feeds; the vertical file is for full-screen placements only;
- check a phone-sized still (`ffmpeg -ss <t> -i film-hd.mp4 -frames:v 1 -vf scale=390:-1 phone.png`) and the
  `sheet` command's frame sheet before handing over.

### Recording a signed-in app

The person signs in; filmwright never types credentials. Import or refresh the session **right before**
recording: a saved token lasts hours, and a sign-in anywhere else usually invalidates the refresh token. The
runner refuses an expired session rather than quietly recording the app signed out; if it does, ask the person
to sign in again, then re-import. Blur or hide the account chip (`recording.redact`), never click anything that
writes to the account during a recording of a live site, and frame the camera so a header with a sign-in state
is out of shot.

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
- two or three stills (`ffmpeg -ss <t> -i <file> -frames:v 1 still.png`) for text fit and layout, and for a
  `both` film the frame sheet (`python -m filmwright.hybrid.film film.yaml sheet`): every segment's two frames
  with its narration on one page, which is also what to show the person for sign-off;
- for a phone cut, one still scaled to 390 px wide: can you read the row the narration is describing?
- listen to the first section; rephrase any sentence the build flags as unclear.

Deliverables are in `<dir>/out/final/` (listed in `manifest.json`). Report each file's length and any check that
needed attention.
