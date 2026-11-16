# Papyrus

- Sources: `f4forge papyrus sources build` extracts the Creation Kit's Base.zip and DLC zips into the forge cache [fact:papyrus.official_sources]
- F4SE's script additions are merged into the vanilla scripts the way F4SE's build does it [fact:f4se.scripts_merge]
- Import order: project source, F4SE, game Source/User, game Source, cache [fact:papyrus.official_sources]
- Compile: `f4forge papyrus compile` uses PapyrusCompiler 2.8.0.4 when the Creation Kit is installed, Caprica otherwise [fact:papyrus.compilers]
- Diagnostics come back as file/line/column/message JSON from both compilers [fact:papyrus.compilers]
- Caprica fails on some folder paths with ios_base::failbit; the forge retries from a fresh copy [fact:papyrus.caprica_failbit]
- Caprica reads 'Parent' as a keyword (F4SE ConnectPoint.parent); use the official compiler for scripts that touch it [fact:papyrus.compilers]
- Flags file: Hidden 0, Conditional 1, Default 2, CollapsedOnRef 3, CollapsedOnBase 4, Mandatory 5 [fact:papyrus.flags]
- PEX: little-endian, version 3.9, game id 2; `f4forge papyrus pex <file>` shows source and objects [fact:papyrus.pex_layout]
- Without the Creation Kit: Champollion decompiles game scripts for imports (sample: names matched 49/49) [fact:papyrus.decompiled_sample]
- Ship compiled .pex under Scripts/; sources only under Scripts/Source [fact:papyrus.pex_layout]
