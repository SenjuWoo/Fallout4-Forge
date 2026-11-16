# Hand-off to the AI starter bundle

Fallout 4 Forge registers itself through `uabs-companion.json` (schema 1, id `fallout4-forge`) once its folder is
under one of the bundle's tool roots. These two rows are ready for the bundle's maintainer to add to the bundle's
own registry and to the `ai-tooling-stack` skill. This repository does not edit the bundle.

## Registry row (`BUNDLED-TOOLS/COMPANIONS.json`, key `fallout4-forge`)

```json
{
  "root_env": "FALLOUT4_FORGE_ROOT",
  "title": "Fallout 4 Forge",
  "repo": "https://github.com/SenjuWoo/Fallout4-Forge",
  "install": {"kind": "source_zip", "asset": "Fallout4-Forge-*-source.zip", "entrypoint": "START-HERE.bat"},
  "update": {"entrypoint": null, "note": "update the checkout (git pull or a newer source zip), then run Install.ps1 again; it keeps the .venv, the forge home and the tools folder and backs up the installed skill"},
  "doctor": {"entrypoint": ["python", "-m", "f4forge", "doctor"]},
  "markers": ["f4forge.cmd", "src/f4forge"],
  "capabilities": {"cli": "f4forge", "mcp": false, "skills": "fallout4-forge", "gui": false},
  "requires": ["python>=3.10"],
  "platforms": ["windows"],
  "notes": "Fallout 4 mods: plugins (Spriggit YAML + Mutagen worker), Papyrus, F4SE native, BA2, textures, materials, meshes, audio, MCM, RobCo Patcher, Base Object Swapper, packaging and deploy.",
  "launch": [{"name": "f4forge", "launcher": "f4forge.cmd"}]
}
```

## `ai-tooling-stack` table row

| Domain | Repository (github.com/SenjuWoo/...) | Start | Find it |
|---|---|---|---|
| Fallout 4 mods: plugins and records (Spriggit YAML, Mutagen worker), Papyrus (official compiler or Caprica), F4SE native plugins (CommonLibF4), BA2 archives, textures, BGSM/BGEM, NIF meshes, voice files, MCM, RobCo Patcher, Base Object Swapper, LooksMenu, BodySlide, FOMOD, Nexus pages, crash logs | `Fallout4-Forge` | `f4forge doctor`, then `f4forge plan "<task>"`; skill `fallout4-forge`; needs your Fallout 4 install (the Creation Kit unlocks the official compiler, Archive2 checks, voice and previs) | `FALLOUT4_FORGE_ROOT` if set, else `UABS_TOOL_ROOTS` |

The skill's description line should also name Fallout 4 next to the other forge games.
