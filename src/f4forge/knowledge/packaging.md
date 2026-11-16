# Packaging

- `f4forge package` zips data/ deterministically (sorted, fixed times), writes a receipt and validates the zip [fact:package.rules]
- Never ship PLAN/STATE/CHANGELOG, f4forge.json, logs, .blend/.psd, or .psc outside Scripts/Source [fact:package.rules]
- `--archives` packs <Plugin> - Main.ba2 and <Plugin> - Textures.ba2 (v1); F4SE, MCM and Tools files stay loose [fact:ba2.layout.v7v8]
- `--fomod` adds info.xml and ModuleConfig.xml; data/Options/<Name>/ folders become optional choices [fact:package.rules]
- `f4forge validate <zip> --simulate` checks any mod zip and simulates a FOMOD install [fact:package.rules]
- The scan rejects private user paths and API keys [fact:package.rules]
- Evidence tiers: static, compile, package; load and gameplay are claimed only after an in-game test [fact:ba2.writer.crosscheck]
- `f4forge bump patch` updates versions and keeps the last good zip in dist/last-good [fact:package.rules]
