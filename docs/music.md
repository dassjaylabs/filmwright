# Music

Every film can get an original score, composed on your machine for the mood you choose and locked to the film's
scene changes. Nothing is sampled or downloaded: every instrument is synthesised with NumPy, so there is nothing
to license and the same inputs always give the same track.

No AI music model is used, on purpose. Local music models are several gigabytes, often licensed for
non-commercial use only, give a different track every run and can't place a downbeat on an exact cut. The composer
has none of those problems and needs no setup. A demo film can use your own track instead (`music: {file: ...}`,
see [film.md](film.md)).

```yaml
music:
  mood: upbeat          # upbeat | calm | corporate | inspiring | playful | epic | sad | suspense | none
  sync_to_scenes: true  # a new section on every scene change
  level: -20            # optional: dB under the narration (auto: -20 for a score, -26 for an ambient bed)
```

## Moods

| mood | tempo | key | feel |
|---|---|---|---|
| `upbeat` | 120 | C major | four-on-the-floor groove, plucked arpeggios, off-beat stabs, risers into each cut and an impact on it |
| `calm` | 76 | A minor | slow pads and bells, no drums; a soft chord marks each scene change |
| `corporate` | 110 | D major | light drums, piano eighths, pulsing bass, gentle swells into cuts |
| `inspiring` | 96 | G major | piano over strings, light drums, swells and soft impacts |
| `playful` | 126 | F major | swung marimba, shaker, bouncing staccato bass |
| `epic` | 84 | D minor | half-time drums with low toms, strings, brass stabs, risers and heavy impacts |
| `sad` | 66 | A minor | slow piano over soft strings, no drums |
| `suspense` | 92 | C minor | ticking hats, a dark ostinato, drone and glassy pings; tension into every cut |

`python -m filmwright.core.music list` prints the same list.

## How it follows the picture

- Every cut (scene change) starts a new section on its own downbeat. Sections start **exactly** at the cut times
  and each keeps its own beat grid, so the music follows the edit. If you'd rather move the edit to the music, snap
  the cuts first (`snap_cuts()` or `--snap`) and use the snapped times for the scenes too.
- The first section is a lighter intro and the last is the fullest. Middle sections rotate through the mood's
  chord progressions, so a long film doesn't loop the same four bars.
- Moods that build add a riser (or a softer swell) over the beat before each cut and drop the kick for the last
  half beat; moods with impacts land one on the cut. Moods without drums mark each cut with a soft chord.
- The film ends on a ringing tonic chord.
- Every score is levelled to about -17 LUFS before mixing. The mixer then sets it relative to the narration and
  ducks it a little further while someone speaks.

## Quiet beds

For a long walkthrough where the music should be felt rather than heard, `ambient()` makes a slow bed with no beat
and no sections: `calm`, `bright`, `focus`, `sad`, `tense` (any score mood name maps to the nearest bed).

## From Python or the command line

```python
from filmwright.core.music import score, ambient
score("music.wav", seconds=42.0, cuts=[6.5, 14.0, 23.2, 35.0], mood="inspiring")
ambient("bed.wav", seconds=180, mood="calm")
```

```bash
python -m filmwright.core.music render --mood sad --seconds 30 --cuts 0,8,16 out.wav
python -m filmwright.core.music render --ambient --mood calm --seconds 120 bed.wav
```

## Adding a mood

Add a `Mood(...)` entry to `src/filmwright/core/music/moods.py`: tempo, key, scale, four-chord progressions in
Roman numerals, and the arrangement switches (drums, bass, lead, pad, stabs, risers, impacts, brightness, reverb,
swing). The composer needs nothing else. Add it to the table above, and run `pytest tests/test_music_*.py`.

## Sound effects

`filmwright.core.sfx` synthesises the small sounds the pipelines use (click, whoosh, chime, pop, tick, swish, riser,
impact, a short sting in and out). `python -m filmwright.core.sfx out.wav whoosh` renders one to listen to.

`sound_effects` in `reel.yaml` picks which ones a film gets:

| setting | sounds |
|---|---|
| `subtle` (default) | click, pop, tick and chime: quiet interface sounds that follow the action |
| `full` | also whoosh, swish, riser and impact on zooms and scene changes |
| `off` | none |
