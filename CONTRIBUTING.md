# Contributing

Thanks for helping. Bug reports, new scene templates, presenter characters, music moods and docs fixes are
all welcome.

## Issues first

Every change starts from an issue, opened with one of the
[issue forms](https://github.com/dassjaylabs/filmwright/issues/new/choose) and titled `area: what goes wrong` (bugs) or
`area: what you'd like` (features), for example `export: OTIO timeline export`. Questions belong in
[Discussions](https://github.com/dassjaylabs/filmwright/discussions). For anything bigger than a small fix, comment on the
issue with your plan before you start, so nobody's work is wasted. Issues marked
[`good first issue`](https://github.com/dassjaylabs/filmwright/labels/good%20first%20issue) are a good start. How issues are
labelled and triaged: [docs/maintaining.md](docs/maintaining.md).

## Set up

```bash
git clone https://github.com/dassjaylabs/filmwright && cd filmwright
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
filmwright setup            # ffmpeg, Chromium, espeak-ng, Rhubarb (prints any admin commands for you to run)
filmwright doctor
```

On Apple Silicon add the neural voices with `pip install -e '.[all]'` and `filmwright setup --voice preset`.

## Before you open a pull request

```bash
ruff check src tests
python -m compileall -q src
pytest
```

- Keep changes focused; one feature or fix per pull request.
- Add or update tests for logic changes (config, music, voice gating, export).
- Templates must stay deterministic: a frame at time *t* is identical on every render.
- Use the fictional example brand (Acme) in examples, docs and screenshots. Don't add real company names,
  logos, people or trademarks.
- Everything bundled must be open source with a license compatible with MIT. Add new components to
  `THIRD_PARTY_LICENSES.md`.
- Never commit sessions (`auth.json`), voice samples, consent records or rendered media.

## Voice cloning

Changes to cloning must keep the consent gate: no option, flag or environment variable may skip it.

## License

The project is MIT licensed (see [LICENSE](LICENSE)). By opening a pull request you agree that your contribution
is licensed under the same MIT license; there is nothing to sign. The filmwright name and logo are not covered by it; see
[TRADEMARKS.md](TRADEMARKS.md).
