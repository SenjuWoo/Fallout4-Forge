# Plugin basics

- Plugins are .esm/.esp/.esl: a TES4 header (HEDR version, masters, flags 0x1 ESM, 0x200 light) then GRUPs of records [fact:plugin.hedr.installed]
- The HEDR record count is not the record total; count with a walk [fact:plugin.hedr_count]
- Fallout4.esm uses HEDR 1.0 and form version 131; the forge writes the same for new plugins [fact:plugin.hedr.installed]
- A project's records live as a Spriggit YAML tree in plugin/; the binary plugin is generated (f4forge plugin build) [fact:ba2.writer.crosscheck]
- New records: `f4forge records new --type MISC --edid MyItem` (worker picks the next free FormID, light range when ESL-flagged) [fact:plugin.light_range]
- Overrides: `f4forge records override <FormKey>` copies the winning record; edit only what you change [fact:load_order.installed]
- Look up before you write: `f4forge records find --index --edid <text>` (467k EditorIDs indexed here) [fact:records.fallout4esm_counts]
- Never edit Fallout4.esm or DLC masters; masters load first in a fixed order [fact:load_order.official_masters]
- Check: `f4forge plugin inspect <p>`, `f4forge plugin esl-check <p>`, `f4forge records validate --target <p>` [fact:plugin.esl_installed_valid]
