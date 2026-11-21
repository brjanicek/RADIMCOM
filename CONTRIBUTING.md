# Contributing to RADIMCOM

Bug reports, ideas and pull requests are welcome. By taking part you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

- **Bugs and feature requests:** open an [issue](https://github.com/om2amr/RADIMCOM/issues/new/choose).
- **Questions and help with setup:** use [Discussions](https://github.com/om2amr/RADIMCOM/discussions).
- **Security problems:** do not open an issue, see [SECURITY.md](SECURITY.md).

For a larger change, please open an issue first so we can agree on the approach before you spend time on it.

## Running from source

RADIMCOM runs on Windows with Python 3.9 or newer.

```bash
python -m venv .venv
.venv\Scripts\pip install -r installer\requirements.txt
.venv\Scripts\pip install --no-deps PyFT8
```

`PyFT8` is needed only for the FT8 decoder.

The third-party binaries in `lib\` and `drivers\` are not in git. Take them from the
[install zip](https://github.com/om2amr/RADIMCOM/releases/latest), or see
[Requirements](docs/installation.md#requirements) in docs/installation.md for their sources. Then use `setup.bat` for the first setup and
`start.bat` to run the receiver.

## Pull requests

- Keep each pull request to one topic.
- Write code, comments and documentation in English.
- Update `README.md` when behaviour changes, and `API/API.md` when the HTTP API changes.
- Do not edit `CHANGELOG.md` or `installer/INSTALL.txt`. For changes users will notice, write the change log text in
  the pull request description under a `## Changelog` heading; the maintainer copies it in after the merge.
- Do not change the version number or build release packages. The maintainer does that.
- Do not commit `data\`, `dist\`, `lib\`, `drivers\`, recordings, logs, dongle serial numbers or anything else from
  your own station.

## Git workflow

The maintainer commits directly to the current version branch while contributors send pull requests to it. These rules
keep the two from conflicting. AI assistants find the same rules in [CLAUDE.md](CLAUDE.md).

- Work happens on the current **version branch** (for example `1.1rc2`), not on `main`, which holds only releases.
  Pull requests go to the version branch.
- In your fork, add the original repository as `upstream`:
  `git remote add upstream https://github.com/om2amr/RADIMCOM.git`
- Start each topic on a fresh branch: `git fetch upstream && git switch -c <topic> upstream/<version branch>`.
  One topic per branch and per pull request, kept short (days, not weeks).
- Before opening the pull request, and whenever the maintainer asks, **rebase** onto the version branch instead of
  merging it in: `git fetch upstream && git rebase upstream/<version branch>`, resolve any conflict, then
  `git push --force-with-lease`.
- After the merge, delete the branch and start the next topic from the latest version branch.
- Put a new feature in its own module and add only the few lines that register it in the shared files `app.py`,
  `static/app.js`, `static/index.html` and `static/style.css`. Do not reformat, reorder or move existing code there
  without agreeing on it first.
- Line endings are handled by `.gitattributes`; do not change them.

## Testing

There is no automated test suite, so please test by hand and say in the pull request what you tested and on which
hardware. Where it helps, include a recording or a sample message for a decoder change.

## Transmitting

Anything that touches transmit code or the TX band limits needs extra care. The limits and the TX disclaimer must stay
in place, and transmit tests should use a dummy load. Please describe these changes in an issue first. See
[NOTICE.md](NOTICE.md).

## Licence

Contributions are accepted under the [MIT License](LICENSE). A new third-party component has to be added to
[NOTICE.md](NOTICE.md) with its licence, and to `installer/make_sources.py` if it is GPL or LGPL and goes into the
release package.
