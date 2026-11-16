# Base Object Swapper

- Rules in Data/<Mod>_SWAP.ini [fact:bos.syntax]
- [Forms]: origBase|swapBase[,swap2]|transforms|chance; [References]: origRef|swapBase|...; [Transforms]: id|transforms|chance [fact:bos.syntax]
- Location filters: [Forms|LocationEDID,CellEDID,KeywordEDID,RegionEDID] [fact:bos.syntax]
- IDs: FormID~Plugin.esp (0x allowed) or EditorID [fact:bos.syntax]
- Transforms pos/posR/posA, rot/rotR/rotA, scale/scaleA (random a/b), flags/flagsC; chance/chanceS/chanceL/chanceR 0-100; NONE for none [fact:bos.syntax]
- Swapping statics and static collections fights precombines; prefer movable objects [fact:bos.syntax]
- Validate: `f4forge validate-config <Mod>_SWAP.ini` [fact:bos.syntax]
- Requirements: Base Object Swapper (Nexus 67528), Baka Framework, F4SE, Address Library [fact:frameworks.installed]
