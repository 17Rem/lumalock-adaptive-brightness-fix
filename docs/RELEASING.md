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

No remote repository is configured by this distribution process. Add the intended repository URL only when ready to publish.
