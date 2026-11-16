# F4SE native plugins

- Entry points: data export F4SEPlugin_Version and F4SEPlugin_Load; F4SEPlugin_Preload optional [fact:f4se.plugin_api]
- `f4forge native new <Name>` copies the pinned commonlibf4-template with the pinned CommonLibF4 [fact:native.template_build]
- `f4forge native build <folder>` runs xmake (MSVC found by xmake) and checks the DLL exports [fact:native.template_build]
- CommonLibF4 is GPL-3.0 with a modding exception: a distributed DLL ships its source [fact:native.template_build]
- Use Address Library IDs, not raw offsets; the bin must exist for each runtime you support [fact:address_library.layout]
- A DLL without version data is skipped by F4SE ('no version data') [fact:f4se.loader_statuses]
- Runtime lines differ (Old-Gen, Next-Gen, Anniversary); test on the runtime you target [fact:runtime.generations]
- Logs: `f4forge logs` explains loader statuses from f4se.log [fact:crash.logs]
