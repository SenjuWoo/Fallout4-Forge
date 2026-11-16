# Leveled lists

- Fallout4.esm holds 2098 LVLI and 228 LVLN [fact:records.fallout4esm_counts]
- Overriding a vanilla list in a plugin conflicts with every other list mod; inject at runtime instead [fact:load_order.installed]
- RobCo Patcher: filterByLLs=<list Plugin|ID>:addToLLs=<item Plugin|ID>~<level>~<count>~<chance> [fact:robco.syntax]
- Removing: removeFromLLs=<item>~<level>~<count>; clear=yes empties a list [fact:robco.syntax]
- Scaffold: `f4forge new <Name> --kind robco` writes a leveledList template [fact:robco.syntax]
- Find lists: `f4forge records find --index --edid LL_ --type LVLI` [fact:records.fallout4esm_counts]
