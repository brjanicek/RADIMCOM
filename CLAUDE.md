# Notes for Claude (and other AI assistants)

Two people work on the same version branch at the same time: the maintainer (om2amr) commits to it directly and
contributors send pull requests from their forks. Follow the git workflow below exactly, so the two never conflict.
The full rules for people are in [CONTRIBUTING.md](CONTRIBUTING.md#git-workflow).

## Which branch

- The active development branch is the current version branch (now `1.2beta3`), not `main`. `main` holds only
  releases. Check `git branch -r` for the newest `origin/<version>` branch if unsure, and ask if it is not clear.
- In a fork, the original repository is the remote `upstream` (`https://github.com/om2amr/RADIMCOM.git`). Add it if it
  is missing.

## Contributor workflow (pull requests from a fork)

1. Start every topic from a fresh branch off the latest version branch:
   `git fetch upstream && git switch -c <topic> upstream/1.2beta3`
2. One topic per branch and per pull request. Keep it short: days, not weeks.
3. Before opening the PR, and again whenever the maintainer asks, rebase instead of merging:
   `git fetch upstream && git rebase upstream/1.2beta3`, resolve any conflict in your branch, then
   `git push --force-with-lease`. Never merge the version branch into the topic branch.
4. Open the PR against the version branch (`1.2beta3`), not `main`.
5. After the PR is merged, delete the topic branch and start the next topic from step 1. Do not keep working on a
   merged branch.

## Files that only the maintainer changes

To avoid the most common conflicts, a pull request must not edit these:

- `CHANGELOG.md` and `installer/INSTALL.txt`: write the change log text in the PR description under a
  `## Changelog` heading instead. The maintainer copies it in after the merge.
- The version number, `installer/make_installer.py` and release packages.

## Keeping conflicts away

- Put a new feature in its own module (`xyz.py`, its own JS/CSS block) and add only the few lines needed to register it
  in the shared files `app.py`, `static/app.js`, `static/index.html` and `static/style.css`.
- Do not reformat, reorder or move existing code in the shared files, and do not rename things there as a side
  effect. Changes like that are agreed first and done while no PR is open.
- Do not touch line endings; `.gitattributes` handles them.

## Maintainer workflow (om2amr, working directly on the version branch)

- `pull.rebase=true`, `rebase.autoStash=true` and `rerere.enabled=true` are set in the local git config.
- Pull before starting work and before every push (`git pull` rebases). Commit and push in small steps, not one big
  commit after several days.
- Never force-push the version branch or `main`.
- When a contributor's PR conflicts, ask them to rebase (step 3 above) rather than resolving it in the merge.
- After merging a PR, copy its `## Changelog` text into `CHANGELOG.md` and `installer/INSTALL.txt` and credit the
  contributor.

## Project conventions

- Code, comments and documentation in English.
- Never commit `data\`, `dist\`, `lib\`, `drivers\`, recordings, logs or anything from your own station.
