# Weapons and weapon mods

- Fallout4.esm holds 252 WEAP, 2409 OMOD, 57 AMMO, 2161 COBJ [fact:records.fallout4esm_counts]
- Find a base: `f4forge records find --index --edid 10mm --type WEAP` [fact:records.fallout4esm_counts]
- Prefer new OMODs over editing vanilla ones that many weapon mods override; check with `f4forge conflicts` [fact:load_order.installed]
- Stat changes without a plugin: RobCo Patcher weapon folder (attackDamage, setNewAmmo, keywordsToAdd) [fact:robco.syntax]
- OMOD names: RobCo objectModification patches filter by name text [fact:robco.syntax]
- AWKCR is installed here and supplies shared keywords [fact:frameworks.installed]
