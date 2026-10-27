# Demo walkthroughs (screen-recorded)

Demo mode records your real product in a browser and turns the recordings into a narrated film: a scenario runner
drives the app with Playwright, a recorder captures each scenario as a sharp video with a log of where every step
happened, and the film builder narrates, zooms, labels and assembles it.

It produces four things:

1. `results.md` / `results.json`: one row per scenario (what was tried, what was expected, pass / fail / skipped,
   evidence). A demo run doubles as a browser test.
2. `videos/<scenario>.mp4` + `<scenario>.events.json`: a real-time recording of each scenario and its event log.
3. `<name>.mp4`, `<name>.srt` and `<name>-voiceover.m4a`: the narrated walkthrough, its subtitles and the narration alone.
4. A poster PNG and a teaser GIF.

Try it on the bundled sample app first: `examples/demo-app/README.md`.

## The steps

1. **Scenarios.** Write `scenarios.yaml`: the app's URL, the viewport, recording settings and a list of scenarios, each
   a list of steps (`goto`, `click`, `type`, `expect_text`, `api`, ...). Start from
   `src/filmwright/templates/demo/scenarios.example.yaml`; every step is in docs/scenario-dsl.md. Cover the happy path,
   the edge cases the code handles, and one control case where the feature should show nothing.
2. **Sign in** (if the app needs it): `python -m filmwright.demo.login --base-url <url> --run-dir .` opens a browser
   window where you sign in yourself; the session is saved to `auth.json`. Sign in (or re-import) right before
   recording: a saved access token lasts hours, and signing in somewhere else usually invalidates the refresh
   token too. The runner reads the token's expiry and refuses an expired session instead of recording the app
   signed out (`--allow-expired`, on the runner or `filmwright build`, overrides; `auth.token_js` tells it which key
   holds the token).
3. **Record:** `python -m filmwright.demo.run_scenarios scenarios.yaml` (add `--only S02,S03` to re-run some). Each
   scenario runs in a fresh, headless browser context. Look at a failure's screenshot and video before deciding
   whether the product or the scenario is wrong.
4. **Write the narration** from what the recordings actually show, one section per clip, in `video.yaml` (start from
   `src/filmwright/templates/demo/video.example.yaml`). Short sentences, numbers written the way they're spoken, about
   2.5 words per second of clip.
5. **Direct the film** (docs/film.md): zooms happen automatically on every real action; add a callout or spotlight
   only where the UI's meaning isn't obvious, and an explainer scene for an idea the app doesn't show.
6. **Build:** `python -m filmwright.demo.build_video video.yaml`.
7. **Check** two or three stills (`ffmpeg -ss <t> -i film.mp4 -frames:v 1 still.png`) and listen to the first section.

`filmwright build` runs steps 3, 6 and the exports for you from reel.yaml.

## Guardrails

- **Test environments only.** The runner refuses hosts that look like production unless they are listed under
  `allow_hosts`. Record production only read-only, with a demo account, and with the site owner's permission.
- **You sign in, filmwright doesn't.** It never types credentials. The saved session (`auth.json`) holds a live token:
  it stays in the run folder (chmod 600), is ignored by git, and is never printed.
- **Destructive steps only on test data** you created for the recording.
- **Private data:** `recording.redact` blurs CSS selectors while recording; `recording.hide` removes them. Check a
  still afterwards: redaction is only as good as the selectors.

## Files

| Module | What it does |
|---|---|
| `filmwright.demo.run_scenarios` | the Playwright scenario runner |
| `filmwright.demo.recorder` | the 4K screencast recorder (also records animated HTML scenes frame by frame) |
| `filmwright.demo.login` | one-time sign-in that saves `auth.json` |
| `filmwright.demo.import_chrome_session.sh` | copies a session from your own signed-in Chrome (macOS) |
| `filmwright.demo.guard` | the test-environment check |
| `filmwright.demo.effects` | zooms, callouts, spotlights, badges anchored to the event log |
| `filmwright.demo.cues` | word timings and the host's gestures from the narration |
| `filmwright.demo.build_video` | narration + cards + clips + effects + music → MP4, SRT, M4A |
| `filmwright.presenter` | the talking-head host (docs/presenter.md) |
| `filmwright.series` | branded intros/outros, explainer scenes, numbered series (docs/series.md) |
| `filmwright.core.export` | 4K/HD, 9:16, 1:1, web and GIF renditions |
