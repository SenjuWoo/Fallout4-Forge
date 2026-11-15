---
name: fallout4-forge
description: Make, check, package and ship Fallout 4 mods with the f4forge CLI (plugins, Papyrus, F4SE, archives, textures, materials, meshes, audio, MCM, RobCo Patcher, Base Object Swapper). Use for any Fallout 4 mod request.
---

# Fallout 4 Forge

Version: 0.1.0

Cold start: `f4forge doctor`, then `f4forge plan "<request>"`, then `f4forge knowledge <topic>`.
Every command prints JSON; exit 0 ok, 1 findings, 2 named failure, 3 forge bug.

The game folder and its Data are read-only. Only `f4forge deploy` and `f4forge ck` write into
the game, each a dry run until `--approve`.
