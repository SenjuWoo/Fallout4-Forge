# Meshes and BodySlide

- Fallout 4 NIFs: 20.2.0.7, user version 12, BS version 130 [fact:mesh.nif_header]
- `f4forge nif info` shows blocks and strings; `f4forge nif refs` checks material and texture paths [fact:mesh.nif_header]
- Blender: `f4forge mesh import|export|roundtrip` uses PyNifly from the tools folder, never installed into Blender [fact:mesh.pynifly_headless]
- PyNifly writes texture paths without the textures\ prefix; the forge resolves both forms [fact:mesh.pynifly_headless]
- 275k NIF paths are installed; check name clashes with `f4forge conflicts` [fact:assets.installed_counts]
- BodySlide presets: SliderPresets/<n>.xml (Preset name/set, SetSlider name/size big|small/value) [fact:data.kinds_installed]
- Slider groups: SliderGroups/<n>.xml (Group name, Member name) [fact:data.kinds_installed]
- LooksMenu presets: F4SE/Plugins/F4EE/Presets/<n>.json (Gender, HeadParts, Morphs, Tints, Weight...) [fact:data.kinds_installed]
- Validate any of them: `f4forge validate-config <file>` [fact:data.kinds_installed]
