# Changelog

## 0.1.0 (unreleased)

First public release.

- `stems` output: the narration, music and sound effects as separate WAVs beside each film, aligned to it and at
  their levels in the mix, for finishing in another editor.
- Read-back check works in every language: it compared only English letters and digits, so Japanese, Chinese,
  Korean and Russian lines all scored a perfect match, and Chinese and Japanese lines over about 3.5 seconds were
  taken for runaway takes. Accent marks are ignored when comparing, and clone samples are transcribed in their own
  language. (Reported by a user.)
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
