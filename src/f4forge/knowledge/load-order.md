# Load order

- Official masters load first: Fallout4, DLCRobot, DLCworkshop01, DLCCoast, DLCworkshop02, DLCworkshop03, DLCNukaWorld, DLCUltraHighResolution [fact:load_order.official_masters]
- Then installed Creation Club plugins from Fallout4.ccc, then starred plugins.txt entries [fact:creation_club.ccc]
- This install: 552 active (7 + 173 + 372), 115 full and 437 light, no missing masters [fact:load_order.installed]
- `f4forge loadorder` reports missing files and masters; it never reorders [fact:load_order.installed]
- Vortex deploys into Data here; a direct deploy may be reverted by its next deployment [fact:mod_manager.vortex.installed]
- Contested overrides of your plugin: `f4forge conflicts` [fact:load_order.installed]
