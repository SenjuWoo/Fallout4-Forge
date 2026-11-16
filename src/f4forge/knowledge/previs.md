# Precombines and previs

- Editing a cell with precombined geometry breaks previs (flicker, vanishing buildings) [fact:creation_kit.switches]
- `f4forge check` warns when a plugin overrides CELL records [fact:creation_kit.switches]
- Regenerate with the Creation Kit: -GeneratePreCombined:<plugin> clean|filtered all|main|ints|other, then -CompressPSG and -BuildCDX [fact:creation_kit.switches]
- Then -GeneratePreVisData:<plugin> with the same options [fact:creation_kit.switches]
- `f4forge ck precombine|previs --plugin <p>` prints the argv (dry run) and runs it with --approve, listing written files [fact:creation_kit.switches]
- CKPE (staged) supports Creation Kit 1.11.246 [fact:creation_kit.ckpe]
- PRP (Previsibines Repair Pack) is installed here; patch against it [fact:frameworks.installed]
- BOS swaps of statics break precombines [fact:bos.syntax]
