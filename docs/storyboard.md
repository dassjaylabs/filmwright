# Storyboards

Before you spend render time, get the script, pacing and look approved:

```bash
filmwright storyboard my-film          # -> my-film/out/storyboard/index.html and storyboard.pdf
filmwright storyboard my-film --no-pdf # the page only
filmwright storyboard my-film --only 2 # story explainers: just story 2
```

The board has one panel per scene:

- a still of the scene;
- its timing, e.g. `0:06–0:11 · 5.0s`;
- the narration line;
- any text shown on screen;
- a space for notes.

It ends with an *Approved by / Role / Date* box. The PDF is A4 landscape, eight panels to a page, for sending
round or printing.

| film type | timings | pictures |
|---|---|---|
| explainer (story, montage) | real: the narration is generated first | the animated scene, rendered at that moment |
| both | real | animated scenes, and a frame from each recording |
| demo | estimated from the length of each line (no narration needed) | a frame from each recording, once recorded |

The narration is cached, so the `filmwright build` that follows an approved storyboard doesn't generate it again.
Change a line in the script and only that line is re-voiced.

The storyboard also runs in CI's smoke test, with the system voice.
