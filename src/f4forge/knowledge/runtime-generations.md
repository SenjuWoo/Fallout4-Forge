# Runtime generations

- Lines: Old-Gen up to 1.10.163, Next-Gen 1.10.980-984, Anniversary 1.11.x [fact:runtime.generations]
- This install: Fallout4.exe 1.11.240.0 (Steam build 24564252) [fact:runtime.version.installed]
- F4SE ships one DLL per runtime (f4se_1_11_240.dll); its version resource reads 0.A.B.C [fact:f4se.layout]
- Installed F4SE 0.7.9 matches the runtime [fact:f4se.version.installed]
- Native plugins need the Address Library bin for the runtime (version-1-11-240-0.bin present) [fact:address_library.layout]
- F4SE plugins declare their runtimes in F4SEPlugin_Version; incompatible ones are disabled with a named status [fact:f4se.loader_statuses]
- `f4forge game` reads all of this; run it after every game patch [fact:runtime.version.installed]
