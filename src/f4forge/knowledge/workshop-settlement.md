# Workshop and settlements

- Build menus are FLST records named WorkshopMenu01* [fact:workshop.menus]
- Each buildable is a COBJ (2161 in Fallout4.esm) [fact:records.fallout4esm_counts]
- New object: `f4forge records new --type COBJ --edid MyBuildable` [fact:workshop.menus]
- Adding to vanilla FLSTs in a plugin conflicts; Workshop Framework and SS2 (installed) offer injection [fact:frameworks.installed]
- Find menus: `f4forge records find --index --edid WorkshopMenu01` [fact:workshop.menus]
