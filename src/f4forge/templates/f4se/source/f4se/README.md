# __NAME__ native plugin

- Scaffold (if missing): `f4forge native new __ID__ --out source/f4se/__ID__`
- Build: `f4forge native build source/f4se/__ID__` (xmake finds MSVC; the result is checked for F4SE exports)
- Ship: copy the DLL to `data/F4SE/Plugins/` and publish this source (GPL-3.0 with modding exception).
