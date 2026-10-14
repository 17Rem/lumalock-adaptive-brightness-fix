# Preparing a public release

This directory is a standalone source repository. Publish this repository, not its parent research workspace. Its Git history starts here; do not merge or import earlier research history.

Before publishing:

1. Run `python -B -m unittest discover -s tests -v`.
2. Review `git status --short`, `git ls-files` and the complete history to be published.
3. Verify the profile checksum and the vendored hashes in `lumalock/vendor/gpu_aux/SOURCE.json`.
4. Keep firmware dumps, LUT backups, transaction logs, recovery state, photographs, screenshots, local paths, credentials and personal device identifiers out of tracked files and release attachments.
5. Keep MIT notices with the code. Label AMD, Intel and Linux as experimental until hardware evidence supports a stronger claim.
6. Review the author name and email in commit metadata before pushing.

Default runtime data is outside the source tree. `.gitignore` is an additional safeguard, not a substitute for reviewing a ZIP or Git history. A source archive made from a reviewed commit with `git archive` avoids accidentally bundling untracked files or the `.git` directory.

## Windows portable build

Use Windows x64 and 64-bit CPython with Tcl/Tk. Install `requirements-build.txt`, then run:

```powershell
python -B -m unittest discover -s tests -v
python scripts/build_windows.py
```

The build creates `dist/LumaLock-<version>-windows-x64.zip` and `dist/SHA256SUMS.txt`. Publish these two files in GitHub Releases; keep build output out of Git. The ZIP contains `LumaLock.exe`, its `_internal` runtime, documentation and licenses. Always extract the whole directory. GPU driver libraries and device backups are not bundled. The EXE is currently unsigned.

The PyInstaller spec explicitly includes the hash-only profile, documentation and notices. It does not collect the parent workspace, user state or tests. Run the extracted executable from a directory with spaces and non-ASCII characters, verify the GUI opens, and check `--guard` starts and exits independently using synthetic completed/pending state files before publishing. Never use an expired synthetic state with a real target identity.

Frozen recovery invokes the EXE with `--guard`, without Python interpreter flags. It uses `PYINSTALLER_RESET_ENVIRONMENT=1` so it does not depend on the GUI process remaining alive. Windowed standard streams are initialized before entering transaction code. See [PyInstaller's subprocess guidance](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html).
