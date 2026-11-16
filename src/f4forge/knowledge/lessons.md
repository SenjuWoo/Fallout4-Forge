# Lessons from building the forge

- F4SE's source keeps only script additions; merge them into vanilla before importing [fact:f4se.scripts_merge]
- Caprica: path-dependent failbit, and 'Parent' as a keyword [fact:papyrus.caprica_failbit]
- PyNifly needs addon_utils.enable for headless use; its export returns an empty set on success [fact:mesh.pynifly_headless]
- The HEDR count is not a record count [fact:plugin.hedr_count]
- Vanilla also ships JSON-text materials [fact:material.json_text]
- DX10 chunking follows mip area, not bytes [fact:ba2.dx10_chunks]
- MCM corpus: 3 of 44 installed configs carry real defects; validate before shipping [fact:mcm.installed_check]
- One official test script indents its ScriptName line; the cache patches it [fact:papyrus.official_sources]
