# Releasing Aquafinder

How a new version goes from the `topbar` branch to a tagged release on `main`. Releases are
numbered `X.Y`, the last tag plus 0.1 unless there's a reason to jump (`git tag` lists them).

Development happens on `topbar`. `main` only receives merges of `topbar` through pull requests.

## 1. Rebuild the script

```sh
git checkout tools/released.txt
python3 tools/mkinstaller.py
```

`tools/released.txt` lists every patched fingerprint a release has shipped, so the installer can
upgrade files patched by an older version. `mkinstaller.py` appends each build's fingerprints to it,
so builds made while developing leave lines that were never released. Reset it to the last commit
first and run `mkinstaller.py` once. `git diff tools/released.txt` should then show only the new
release's fingerprints. Never remove lines that are already committed.

## 2. Build the app, package and dmg

The app and package need a Panther Mac with the Developer Tools (see "For developers" in the
README). With the Panther VM:

```sh
AQ_SSH="ssh -F vm/ssh/config panther" tools/mknative.sh X.Y
```

The version argument fills `__VERSION__` in `gui/Info.plist` and `pkg/Info.plist` and names the
disk image's volume "Aquafinder X.Y". The result is `dist/Aquafinder.dmg`.

The VM sleeps after 10 idle minutes. Wake it with `tools/qmon.sh "sendkey shift"` before building.
During a long build, nudge it now and then with `tools/qmon.sh "mouse_move 1 0"`.

## 3. Test on Panther and Tiger

On both VMs:

1. Copy `dist/Aquafinder.dmg` over and open it.
2. Check that the package's copy of the script is the one just built: its md5 matches
   `dist/aquafinder.sh`. It's `Aquafinder.pkg/Contents/Resources/aquafinder.sh` on the disk image.
3. Install the package, restart, and run `sh aquafinder.sh status`. Every part should read
   "Aquafinder installed".
4. Open the Aquafinder app. Every row should be available, and it should switch parts and sidebar
   styles on and off.
5. Look over what changed in the release in a Finder window: list, icon and column view, an
   inactive window, a collapsed and moved sidebar.

An Aquafinder app left over from an older version reports newer files as "not recognised". That's
expected until the new package is installed.

## 4. Screenshots and README

If the release changes how things look, update `screens/`, rerun `python3 tools/previews.py` for
the app's before/after pictures in `gui/preview/`, and update `README.md`.

## 5. Commit and tag

Commit everything on `topbar`, titled `Version X.Y: <headline>`, with a short list of what changed
for users. Tag that commit with a lightweight tag:

```sh
git tag vX.Y
```

## 6. Push

```sh
git push origin topbar
```

```sh
git push origin vX.Y
```

## 7. Pull request and merge

First check what `main` has that `topbar` doesn't:

```sh
git log --oneline topbar..origin/main
```

It should list only merge commits from earlier pull requests. If it lists anything else, merge
`main` into `topbar` first.

```sh
gh pr create --base main --head topbar --title "Aquafinder X.Y: <headline>"
```

In the body, describe the new features and say what was tested on which system. Then merge with a
merge commit, as for every earlier release:

```sh
gh pr merge <number> --merge
```

Finally, bring the local `main` up to date and keep working on `topbar`:

```sh
git fetch origin && git branch -f main origin/main
```

The `vX.Y` tag stays on the `topbar` commit. The merge commit on `main` has the same files.

## 8. GitHub release

Publish a release for the tag, with the disk image and the script attached:

```sh
gh release create vX.Y dist/Aquafinder.dmg dist/aquafinder.sh --verify-tag --latest --title "Aquafinder X.Y" --notes-file notes.md
```

Write the notes like the earlier releases':

- One line on what Aquafinder is.
- `## New in X.Y`: what changed, for users, each item saying whether it's on Panther, Tiger or both.
  If a version was never published as a release, add its own section too.
- Screenshots of anything new, from `https://raw.githubusercontent.com/Caipe97/Aquafinder/vX.Y/screens/...`.
- `## Install`: the three installer steps, the Terminal alternative, and that it's only for
  10.3.9 and 10.4.11.
- The disk image's checksum, as `md5 dist/Aquafinder.dmg` prints it.

Then download the attached disk image from the release and check that its md5 matches.
