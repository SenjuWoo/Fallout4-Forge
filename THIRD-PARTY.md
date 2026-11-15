# Third-party notices

The forge ships no third-party code, binaries or game data. Its release is a
source archive built by `git archive`.

- **PyYAML** (MIT) is installed as a Python dependency.
- Tools listed in `tools.lock.json` (xEdit, Spriggit, Champollion, Caprica,
  DirectXTex, PyNifly, CommonLibF4 and its template, the F4SE source and the
  optional tools) are downloaded by `f4forge tools sync` from their upstream
  releases at pinned versions and SHA-256 hashes, under their own licences. They
  are never redistributed by this repository.
- The records worker restores **Mutagen.Bethesda.Fallout4** (GPL-3.0) from NuGet
  when it is built on the user's machine; it is not vendored.
- **CommonLibF4** is GPL-3.0 with a modding exception. The forge never links it.
  A native F4SE plugin built from the template links it, so a distributed DLL
  ships its source.
- File-format knowledge (BA2, plugin records, PEX, BGSM/BGEM, NIF headers, FUZ)
  was learned from open-source projects named with their commit in
  `src/f4forge/knowledge/SOURCES.json` and confirmed against an installed game.
  No code was copied unless a file says so with its licence.
- Fallout 4, the Creation Kit and their files belong to Bethesda Softworks. The
  forge reads them on the user's machine and never redistributes them. This
  project is not affiliated with or endorsed by Bethesda Softworks.
- Framework names (F4SE, Address Library, MCM, RobCo Patcher, Base Object
  Swapper, LooksMenu, BodySlide, Creation Kit Platform Extended) refer to their
  respective projects and authors.
