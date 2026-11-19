# Installing for a user

1. Read [README.md](README.md) and [THIRD-PARTY.md](THIRD-PARTY.md).
2. Run `./install.sh --dry-run` and describe the printed changes.
3. Tell the user that cass uses an MIT-derived licence with a rider that grants no rights to OpenAI, Anthropic, their affiliates or representatives. Do not accept on their behalf.
4. After explicit acceptance, run `./install.sh --accept-cass-licence`. Add `--yes` only if the user also approved the printed file changes.
5. Run `wsm doctor --json` and inspect the result.
6. Run `wsm init` in each workspace that should have a journal. Use `wsm private add PATH` before indexing an NDA or otherwise excluded workspace.

If an agent configuration file is a symlink, the installer skips it. Report the link and ask the user to add `templates/instructions.md` at the managed source. Do not write through the link.

To reverse the installation, run `./uninstall.sh`. `./uninstall.sh --purge` also removes cass installed by this kit and its local index after confirmation. Neither command deletes workspace journals.
