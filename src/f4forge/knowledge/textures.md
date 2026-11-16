# Textures

- Vanilla formats: _d BC1 (BC3 with alpha), _n BC5, _s BC5, _g BC1, _msn BC3/BC1, _e BC1 or BGRA [fact:texture.roles]
- Vanilla uses UNORM formats, power-of-two sizes and full mip chains [fact:texture.roles]
- Convert: `f4forge tex convert <png> --role diffuse` (texconv, mips generated) [fact:texture.roles]
- Inspect: `f4forge tex inspect <dds>` warns on format, mips and size [fact:texture.roles]
- Texture paths in materials and NIFs are relative to Data/Textures [fact:mesh.nif_header]
- Pack big texture sets into <Plugin> - Textures.ba2 (DX10) [fact:ba2.dx10_chunks]
