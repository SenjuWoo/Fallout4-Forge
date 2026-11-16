# Materials (BGSM / BGEM)

- BGSM (lit surfaces) and BGEM (effects) are binary; the forge reads and writes them byte for byte [fact:material.layout]
- Vanilla materials are version 2; installed mods also use 0, 1 and 3 [fact:material.layout]
- The game also accepts JSON-text materials (vanilla Startup.ba2 has some) [fact:material.json_text]
- Edit as JSON: `f4forge material show <file> --out m.json`, then `f4forge material build m.json --out x.bgsm` [fact:material.layout]
- Projects keep material JSON in source/materials; `f4forge build` writes data/Materials [fact:material.layout]
- Texture fields are Data/Textures-relative; `f4forge check` resolves them against the project and installed archives [fact:assets.installed_counts]
- NIFs name their material in the string table (BSLightingShaderProperty) [fact:mesh.nif_header]
