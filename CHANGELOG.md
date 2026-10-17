# Changelog

## 0.1.0 (unreleased)

First public release.

- `stems` output: the narration, music and sound effects as separate WAVs beside each film, aligned to it and at
  their levels in the mix, for finishing in another editor.
- Read-back check works in every language: it compared only English letters and digits, so Japanese, Chinese,
  Korean and Russian lines all scored a perfect match, and Chinese and Japanese lines over about 3.5 seconds were
  taken for runaway takes. Accent marks are ignored when comparing, and clone samples are transcribed in their own
  language. (Reported by a user.)
- Storyboards: `filmwright storyboard` lays out one panel per scene (a still, the narration line, timing and
  on-screen text) as a page and an A4 PDF with a sign-off box, for approval before the full render. It works for
  every film type; animated films narrate first (cached) to get real timings (#21).
- Voices: a library of 7 ready-made narrators with a plain, natural delivery, `voice: {type: library, name:
  olivia}`. Each is a bundled, checksum-verified synthetic reference clip cloned with the Base model, so it sounds
  the same on every machine (#20).
- Sound: a new `sound_effects` setting, `subtle` by default. Films keep the quiet interface sounds (click, pop,
  tick, chime) and drop the whooshes, swishes, risers and impacts on zooms and scene changes, which distracted from
  the narration; `full` brings them back, `off` removes all effects (#18).
- Music: quieter by default in every film type, 20 dB under the narration for a score and 26 dB for an ambient
  bed (was 12 to 14 dB, and 22). Demo films now bring the narration to a set loudness with a peak limiter, so they
  play at -16 LUFS like the other film types instead of about -24, and the music level is measured against the
  real voice. Measured on the examples, the music now sits about 21 dB under the voice (was 9 to 16) (#19).
- Narration: a take spoken much slower than normal speech (drawn-out words) is now regenerated like a garbled
  one, and the most natural take is kept (#15). The README sample is re-narrated by the library voice `olivia`
  with the quieter mix (#16, #26, from user feedback).
- File names: film names keep the letters of any script, so a Japanese or Russian title no longer becomes
  `film` (#9, contributed). Product names, `file_prefix` and story slugs are made file-safe the same way in
  every film type (a product called `Acme/Tasks` broke the path), the same title always gives the same name
  however its accents were typed, and a series episode slug that can't be a file name is refused with a
  suggestion (#12, #13).
- Demo films: the narration no longer drifts behind the picture and captions from section to section (each
  section's AAC padding was being kept when sections were joined; up to about 60 ms in a 45-second film).

- One command, `filmwright`, with an interactive `new` wizard and a `reel.yaml` config.
- Three film types: screen-recorded **demo** walkthroughs, fully animated **explainers** (story and montage
  formats), and **both** in one film.
- Options: voice (preset, described, cloned with consent, or system), animated talking-head presenter, music
  mood (upbeat, calm, corporate, inspiring, playful, epic, sad, suspense), burned-in captions, and outputs (4K,
  HD, 9:16, 1:1, web, GIF).
- Synthetic-voice disclosure setting: none, metadata or end card.
- Own animation engine (`motion.js`, MIT); everything bundled or installed is open source.
