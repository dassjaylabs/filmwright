# Narration voices

The `voice:` block of `reel.yaml` picks who narrates the film. Everything runs on your machine: no text or audio
is sent anywhere.

```yaml
voice:
  type: preset          # preset | described | clone | system
  speaker: ryan         # preset
  style: "Natural, relaxed and conversational"   # preset: how to deliver the lines
  description: ""       # described: the voice in words
  sample: voice/sample.wav   # clone: a consented sample (see below)
  temperature: 0.65     # 0.3-1.0; lower is steadier
  seed: 7               # another number gives different takes of the same lines
  language: english
```

| type | what you get | needs |
|---|---|---|
| `preset` (default) | a built-in speaker: `ryan`, `aiden` (native English); `serena`, `vivian`, `dylan`, `eric`, `uncle_fu` (Chinese-native), `ono_anna` (Japanese), `sohee` (Korean). The non-English speakers read English with an accent. | Apple Silicon, `filmwright setup --voice preset` (5.8 GB, once) |
| `library` | a ready-made narrator picked by name: `nora`, `james`, `olivia`, `henry`, `priya`, `marcus`, `ethan`, `graham`, `claire` ([below](#library-voices)) | Apple Silicon, `filmwright setup --voice library` (5.8 GB, once) |
| `described` | a voice designed from a sentence, e.g. "Calm, friendly narrator in her thirties, British" | Apple Silicon, `filmwright setup --voice described` (10 GB, once) |
| `clone` | a voice cloned from a short recording of a real person, **with their consent** | Apple Silicon, `filmwright setup --voice clone` (5.8 GB, once), a consented sample |
| `system` | espeak-ng: robotic, but it runs anywhere | `filmwright setup` |

The neural voices are [Qwen3-TTS](https://huggingface.co/Qwen) running on [MLX](https://github.com/ml-explore/mlx)
through [mlx-audio](https://github.com/Blaizzy/mlx-audio). On a machine that can't run them (not an Apple
Silicon Mac, or mlx-audio not installed), `preset` and `described` fall back to the system voice and say so.
A `clone` voice never falls back: if it can't run, the build stops, because a different voice isn't what was asked for.

## How narration is generated

- Each sentence is generated on its own with a fixed seed, so re-renders sound the same.
- Every sentence gets a length sanity check, and Whisper reads it back. A garbled, truncated or runaway take, or a
  drawn-out one (spoken much slower than normal speech), is regenerated (up to three tries) and the best one is
  kept.
- Sentences that never read back cleanly are listed at the end. Listen to those; rephrasing or spelling out an
  abbreviation usually fixes them.
- Finished narration is cached in `<project>/.tts-cache/`, so editing one line only re-voices that line.
- A described voice is rendered once into a short reference clip (kept in the filmwright cache) and that clip is
  used for every sentence, so the voice stays the same across the film.

Write narration for the ear: short sentences, numbers the way you'd say them ("five oh four", "ninety days"),
no symbols.

Hear a voice before building:

```bash
python -m filmwright.core.voice preview --play
python -m filmwright.core.voice preview --type preset --speaker aiden --style "Warm and upbeat" --play
python -m filmwright.core.voice preview --type described --description "Calm, friendly narrator in her thirties" --play
python -m filmwright.core.voice speakers
```

## Library voices

Ready-made narrators with a plain, natural delivery, designed for product and explainer films:

```yaml
voice: {type: library, name: olivia}
```

| name | voice |
|---|---|
| `nora` | American woman, 30s, warm and clear product guide |
| `james` | American man, 30s, relaxed and conversational |
| `olivia` | British woman, 30s, calm and polished presenter |
| `henry` | British man, 40s, steady and trustworthy |
| `priya` | Indian English woman, 30s, bright and clear explainer |
| `marcus` | American man, 40s, deep and assured (B2B) |
| `ethan` | American man, late 20s, bright and friendly (launches) |
| `graham` | British man, early 50s, veteran analyst: deep, unhurried, dry (finance, research, B2B) |
| `claire` | American woman, mid 40s, senior strategist: rich low alto, crisp and composed (finance, data, briefings) |

Each was designed once from a written description with Qwen3-TTS VoiceDesign and ships as a short reference clip
(`src/filmwright/assets/voices/`). A film clones that clip with the Base model, so the voice sounds the same on
every machine and the VoiceDesign model isn't needed. The voices are synthetic and not modelled on any real
person, so they need no consent record. Only the bundled clips, verified by checksum, are treated that way: a
recording of a real person always goes through `clone` and its consent check. `scripts/build_voice_library.py`
rebuilds the library from `library.json`.

Hear one with `filmwright voice preview --type library --name olivia --play`.

## Cloned voices and consent

**Only clone a voice with the explicit permission of the person it belongs to.** Cloning someone's voice without
permission can deceive people, damage reputations and break the law in many places. filmwright makes consent a
hard requirement, not a setting:

- Every way of creating a sample (`record`, `prepare`) asks the speaker to agree to a consent statement, and
  writes `sample.consent.json` next to the sample: the speaker's name, the statement, the time, who created it on
  this machine, where the sample came from, and the sample's SHA-256.
- Clone mode reads that record every time it runs and refuses to start when it is missing, incomplete, or was made
  for a different recording. There is no configuration option that skips this check.
- `forget` deletes the sample, its transcript and its consent record. Delete the project's `.tts-cache/` too to
  remove narration already generated in that voice.

The consent record is an accountability record for your own project, not a legal document. If you clone someone
else's voice, keep their written agreement too.

```bash
python -m filmwright.core.voice.clone passage --terms "Acme, Quick Add"      # text that covers your product's names
python -m filmwright.core.voice.clone record --speaker "Your Name"           # the speaker reads it (needs a microphone)
python -m filmwright.core.voice.clone prepare --input memo.m4a --speaker "Your Name" --i-have-consent   # or an existing recording
python -m filmwright.core.voice.clone check
python -m filmwright.core.voice.clone preview --play
```

A good sample is 10-30 seconds of natural speech in a quiet room, in the register you want the narration in. The
transcript (`sample.txt`) must match what was said; Whisper writes it, and you can correct it by hand.

When a film uses a cloned voice, the default disclosure says so: "Narration uses a cloned voice, used with the
speaker's consent." See [disclosure.md](disclosure.md).

For a full desktop app around voice cloning (text- or audio-to-speech, voice design, streaming, word timestamps),
see [clodio](https://github.com/dassjaylabs/clodio), which runs the same models locally.

## Troubleshooting

- **"mlx-audio isn't installed"**: run `filmwright setup --voice preset` (or `described` / `clone`).
- **A word is mispronounced**: spell it the way it sounds in the narration text, e.g. "Acme Sink" for a product called "AcmeSync".
- **The voice drifts in energy between sentences**: lower `temperature` (0.5 is steadier).
- **The delivery sounds over-excited, or words are drawn out**: ask for a plain delivery in `style` and leave out
  words like "upbeat", "energetic" or "excited" (the README sample uses "Speak at a normal conversational pace in a
  calm, even, natural tone..."; see `docs/media/sample/reel.yaml`), and try `temperature: 0.5`. If one line still
  drags, try another `seed`.
- **The recording is silent**: on macOS, allow microphone access for your terminal app in System Settings > Privacy & Security > Microphone.
