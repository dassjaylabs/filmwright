# Brands

A brand is a folder with `brand.yaml` and `logo.png`. It sets everything that differs between products: colours,
logo, wordmark, headline font, the site to record and how to sign in, what to blur, the host's shirt, the outro line,
the default voice and music, and which effects are on.

filmwright ships one brand, `example`: "Acme", a fictional company. Copy `src/filmwright/brands/example/` to start your
own, then point at it from reel.yaml (`brand: brands/my-brand`) or series.yaml (`brand: my-brand`, a folder next to it).

## Fields

```yaml
name: Acme                                # shown in cards and captions
wordmark: {pre: "ACME", accent: ""}       # the name under the logo; `accent` is drawn in the accent colour
logo: logo.png                            # square icon mark next to this file
logo_radius: 0.22                         # corner rounding of the logo tile (0 for a logo with its own shape)
native: true                              # only for the bundled example: the scenes are drawn in this palette

colors:                                   # hex; the animated scenes are recoloured from these by role
  bg: "#0f1222"                           # page / scene background (darkest)
  bg2: "#171a30"                          # panels
  card: "#22264a"                         # raised cards
  line: "#343a6b"                         # outlines and rules
  ink: "#f4f5fb"                          # main text
  muted: "#a9aecb"                        # secondary text
  accent: "#7c5cff"                       # the one highlight colour
  on_accent: "#ffffff"                    # text drawn on the accent colour
themes: {main: "#7c5cff", alt: "#22c55e", warm: "#ff8a4c"}   # per-episode accents; a spec says `theme: alt`
fonts: {headline: '"IBM Plex Sans", system-ui, sans-serif'}

site:
  base_url: http://localhost:8765         # where the app is recorded
  allow_hosts: [localhost]                # hosts the runner may visit
  public_url: acme.example                # shown on the outro button
  read_only: true                         # false only for a sandbox where changes are fine
auth:
  mode: none                              # none | chrome-session | login-py
  token_js: ""                            # JS returning the bearer token for `api` steps
  token_key: auth_token                   # localStorage key holding the session
  strip_keys: []                          # saved keys to drop from the session file (globs ok)
  chrome_host: ""                         # chrome-session: host substring of the signed-in Chrome tab
  account_check: null                     # {path: /api/me, field: plan, equals: pro}: checked before every recording
redact: []                                # CSS selectors blurred while recording
host: {preset: leo, shirt: "#7c5cff", shirt2: "#5b3fd9"}    # the presenter (docs/presenter.md); enabled: false hides it
outro: {tagline: "Plan less. Ship more.", footer: "Sample data. Acme is a fictional company."}
captions: {disclaimer: ""}                # appended to every social caption file
narration_rules: ""                       # optional path to your notes on what narration must never say or show
music: {mood: upbeat}                     # docs/music.md
voice: {}                                 # overrides for the narration voice, e.g. {style: "Warm and upbeat"}
effects: {sfx: true, jingle: false, verified_badges: false, callouts: true}
wordmark_css: "letter-spacing:.18em;font-weight:600"
```

## Effects switches

| Switch | On means |
|---|---|
| `sfx` | soft clicks and pops under the action (whooshes and swishes too with `sound_effects: full`) |
| `jingle` | a short synthesised sting at the start and end of an episode |
| `verified_badges` | a "Backend verified" pill over passing `api` steps (useful for QA films, not marketing) |
| `callouts` | callout labels and key-phrase chips (zooms and spotlights stay on either way) |

## Colours and recolouring

Pick a dark background ramp (`bg` darkest, then `bg2`, `card`, `line`) and one accent. Scenes keep their semantic
colours (green up, red down, category colours), so an accent that is itself green or red reads less clearly; check a
still of the `bars-shift` scene if you choose one.
