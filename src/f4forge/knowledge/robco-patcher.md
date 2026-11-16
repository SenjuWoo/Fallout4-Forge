# RobCo Patcher

- Runtime record patches without a plugin; INIs in F4SE/Plugins/RobCo_Patcher/<folder>/ [fact:robco.syntax]
- Folders: ammo, armor, formList, ingestible, leveledList, misc, npc, objectModification, race, weapon (+ aimModel, constructibleObject, explosion, projectile) [fact:robco.syntax]
- One patch per line: key=value segments joined by ':'; forms Plugin.ext|FormID; 'none' leaves a field unset; // comments [fact:robco.syntax]
- Leveled lists: filterByLLs=<list>:addToLLs=<item>~<level>~<count>~<chance> [fact:robco.syntax]
- Weapons: filterByWeapons=...:attackDamage=33:keywordsToAdd=... [fact:robco.syntax]
- addToLL is outdated; use filterByLLs + addToLLs [fact:robco.syntax]
- Validate: `f4forge validate-config <ini>` (all 134 installed INIs pass) [fact:robco.syntax]
- Requirements: RobCo Patcher (Nexus 69798), F4SE, Address Library [fact:frameworks.installed]
