# Security

Report a vulnerability through GitHub's private vulnerability reporting on this
repository (Security tab), not in a public issue.

What the forge does and does not do:

- Reads the game folder, its Data, mod-manager staging, logs and mod files;
  writes only to your project, to the forge home (`%LOCALAPPDATA%\Fallout4Forge`
  by default: config, caches, logs, the records worker) and to the tools folder
  it manages.
- Writes into the game folder only through `f4forge deploy` and the `f4forge ck`
  commands. Each is a dry run until `--approve`, writes a receipt, keeps backups
  and refuses to overwrite a file its receipt does not own.
- Runs external programs only when a command needs them (the Creation Kit's
  Papyrus compiler, Archive2, xwmaencode and LipGenerator, Caprica, Champollion,
  Spriggit, texconv, Blender, xmake/MSVC, the .NET records worker). Every run has
  a timeout and receives its arguments as a list, never as a shell string.
- Network access happens only in `f4forge tools sync --approve`, which downloads
  the pinned assets in `tools.lock.json` and verifies each SHA-256 before
  extracting it. `GH_TOKEN` is honoured when set and never printed.
- Scans packages for private paths and common secret formats so you do not
  publish one by accident. It never prints a full secret.
