# Story films: configuration

A story project is a folder with `project.json`, `stories.json` and one output folder per story (`NN-<slug>/`).
`python -m filmwright.explainer.story <dir> init` writes a complete fictional example (three stories for
"Acme Tasks", a team task and scheduling app): `examples/explainer/` in this repository.

## project.json

| field | meaning | default |
|---|---|---|
| `product` | product name, used in narration ("The Acme Tasks way…") | required |
| `wordmark` | text in the logo lockups | brand kit, else `product` in capitals |
| `tagline`, `url` | line under the final wordmark, and an optional address under it | brand kit |
| `file_prefix` | output names: `<prefix>-<slug>-hd.mp4`. Characters that can't be in a file name become dashes | `product`, lower case, made file-safe |
| `brand` | a brand folder name/path (`brand.yaml`, shared with the other film types, see [brands.md](brands.md)) or an inline `{colors: {bg, accent, alt, warm, ink}, logo}` | the example palette |
| `archetypes` | story shapes to rotate through, e.g. `"ABC"` or `"AAB"` | `"ABC"` |
| `stories_per_palette` | consecutive stories that share an office wall colour | 3 |
| `walls` | list of `[top, bottom]` wall gradient colours | six pastel tints |
| `tempo` | narration speed-up (1.0 = as spoken) | 1.06 |
| `voice`, `music`, `talking_head`, `captions`, `outputs`, `checks` | see [explainer.md](explainer.md#options) | |

With no `logo`, the mark is a rounded tile with the wordmark's first letter (`monogram` overrides the letter).

## stories.json

A list of stories. Text fields are spoken unless noted.

| field | example | used in |
|---|---|---|
| `n`, `slug` | `1`, `"support-on-call-rota"` | order, folder and file names (characters that can't be in a file name become dashes) |
| `arch` | `"A"`, `"B"` or `"C"` | optional: force a shape ([shapes](#story-shapes)) |
| `name`, `pron`, `poss` | `"Priya"`, `"She"`, `"her"` | narration; always state pronouns explicitly |
| `role` (on screen), `roleLine` | `"Support team lead"`, `"leads a twelve-person support team that never sleeps."` | name tag, "Meet …" line |
| `style`, `glasses`, `skin`, `skin2`, `hair`, `shirt`, `shirt2` | `"long"`, `true`, colours | the character; styles: `bun`, `short`, `long`, `curly`, `buzz` |
| `problem` | where the work piles up | the pile-up scene |
| `cost` | how long it takes today | the whiteboard clock |
| `stakes` | completes "Not good enough when …" | the workaround verdict |
| `action` | what they do with the product, as a clause: `"asks for next week's on-call rota"` | the result line |
| `need` | shape B: what the manager needs by five | the opening |
| `pile` (on screen) | `{"label": "Shift requests this week", "count": 186, "item": "note"}` | counter and falling items: `note`, `doc`, `mail`, `ticket` |
| `sources` (on screen) | three `[icon, label]` | whiteboard sketches: `doc`, `folder`, `mail`, `sheet`, `db`, `chart`, `book`, `calendar`, `chat`, `phone`, `clock`, `people` |
| `equation` (on screen) | `"1 rota = 1 lost morning"` | handwritten sum |
| `workaround` (on screen) | `{"icon": "sheet", "text": "Copy last week's?", "verdict": "Not good enough"}` | the crossed-out old way |
| `setup` (on screen) | `{"inputs": [[glyph, label] × 3-5], "items": [[title, [chip × 3]] × 3], "badge": "Always up to date"}` | the product scene; glyphs: `calendar`, `chat`, `mail`, `sheet`, `upload`, `people`, `doc`, `bell` |
| `app` (on screen) | see below | the result scene |
| `ping` (on screen) | `{"from", "label", "meeting", "meetingTime", "initials"}` | shape B's opening message |
| `doneLabel` (on screen) | `"Done at 3:12 PM"` | shape B's stamp |
| `beforeLabel`, `afterLabel` (on screen) | `"The old way"` | shape C's split screen |
| `setupLine`, `workaroundLine`, `resultLine`, `afterLine` | full sentences | override the generated lines |
| `lines` | `{"meet": "Say hello to Priya."}` | override any beat's narration |
| `wall` | `["#EEF1FF", "#DCE2FA"]` | this story's wall colours |

### app: the result scene

`app.kind` picks one of four product windows; every kind ends with the person smiling, confetti and the lockup.

| kind | what happens | fields |
|---|---|---|
| `chat` | the request is typed and sent; the result builds word by word with numbered badges linked to two detail cards | `request`, `result`, `cards` (`[[title, meta] × 2]`), `placeholder` |
| `form` | fields fill in one by one, the button is pressed, a result card slides in | `fields` (`[[label, value] × 2-4]`), `button`, `result`, `summaryTitle` |
| `dashboard` | metric tiles count up, bars grow, a trend line draws, a result card slides in | `metrics` (`[[label, value, unit] × 3]`), `result`, `summaryTitle` |
| `checklist` | the request is pressed, steps tick off with a progress bar, a result card slides in | `request`, `steps` (3-5), `result`, `summaryTitle` |

All kinds use `title` (top right of the window) and `result` (two `[bold line, detail line]` pairs, each under
about 48 characters).

## Story shapes

A batch rotates through three shapes so viewers who watch several don't see the same film twice.

- **A. A day in the life** (`meet → pile → cost → workaround → setup → result`): meet the person (name tag); the
  work piles up (falling items, growing stacks, a counter; their face turns worried); a thought bubble opens the
  whiteboard (a spinning clock, three sketched sources, the sum); the usual workaround is crossed out; an eraser
  wipe opens the product (inputs fly into the logo, sorted items come out, a badge); the result scene.
- **B. The 3 o'clock request** (`ping → pile → …`): opens on the laptop at 3:00 PM as a manager's message slides in
  and the 5 pm meeting turns red; the camera pulls out of the screen into the office; ends with a "Done at …" stamp.
- **C. Before and after** (`meet → before → after → result`): the screen splits: "the old way" (whiteboard) on the
  left, the product on the right, which lights up and then fills the screen for the result. Shortest of the three.

Each beat is one or two sentences. Scenes start on the music's beat, and each scene stays on screen long enough
for its animation even when its sentence is short (the captions follow the spoken length).

Write for the ear: short sentences, numbers as they are spoken ("five oh four", "ninety days"), no symbols, and
never the product name alone as a sentence (voices stretch a one-word sentence). Keep each film to about 25 to 40
seconds of speech.

## Adding a shape

1. Name its beats in `SHAPES` and write their lines in `Project.lines()` (`filmwright/explainer/story.py`).
2. In `story.html`, alias new beats to the windows existing scenes expect (see the `ARCH === "C"` block after
   `const B = …`), or add a scene function and call it from `main()` for that shape.
3. Give new scenes a minimum hold in `MIN_HOLD`, render one sample and review it before a batch.
