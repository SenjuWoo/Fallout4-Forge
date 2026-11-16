# Quests and dialogue

- Fallout4.esm: 1336 QUST, 35443 DIAL, 78087 INFO, 3568 SCEN [fact:records.fallout4esm_counts]
- New quest: `f4forge records new --type QUST --edid MyQuest`, then attach a script (Papyrus kind) [fact:papyrus.compilers]
- Prefer a new quest with its own aliases over editing vanilla stages [fact:load_order.installed]
- Voice for INFO lines: Sound/Voice/<Plugin>/<VoiceType>/<INFO>_<n>.fuz [fact:audio.voice_path]
- Make voice files: `f4forge audio voice <wav> --text ... --info <FormID> --voice-type <VT>` [fact:audio.lipgen]
- XDI (Extended Dialogue Interface) is installed here [fact:frameworks.installed]
- Dialogue editing itself needs the Creation Kit; the forge creates the quest record and voice files [fact:creation_kit.layout]
