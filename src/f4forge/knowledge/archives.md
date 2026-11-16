# Archives (BA2)

- Header: BTDX, version, GNRL or DX10, file count, name-table offset [fact:ba2.header]
- Versions 1, 7 and 8 share one layout; the forge writes version 1 by default (every runtime reads it) [fact:ba2.layout.v7v8]
- Name/dir hashes: CRC-32 with init 0, no final XOR, lowercase [fact:ba2.hashes]
- GNRL: .pex, .fuz, .wav, .xwm, strings, .swf, .png, .xml, .dds stay uncompressed like vanilla [fact:ba2.gnrl_stored]
- DX10 chunks: own chunk per mip of >= 512x512 pixels, at most 4 chunks; cubemaps one chunk [fact:ba2.dx10_chunks]
- The forge writer round-trips vanilla archives and Archive2 reads its output with identical payloads [fact:ba2.writer.crosscheck]
- Archives load when named after a plugin: <Plugin> - Main.ba2, <Plugin> - Textures.ba2 (`f4forge package --archives`) [fact:ba2.vanilla_samples]
- F4SE plugins, MCM configs and BodySlide files stay loose [fact:ba2.vanilla_samples]
- Tools: `f4forge ba2 list|extract|verify|pack`; in-game load of forge DX10 archives: NOT RUN yet [fact:ba2.writer.crosscheck]
