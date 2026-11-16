# Light plugins (ESL)

- A light plugin holds new object IDs up to 0xFFF [fact:plugin.light_range]
- The floor is 0x001 when HEDR >= 1.0 and the plugin has a master; otherwise 0x800 [fact:plugin.light_range]
- Installed light plugins: 182 at HEDR 1.0, 6 at 0.95; all pass the range check [fact:plugin.esl_installed_valid]
- An .esl extension or the 0x200 flag makes a plugin light; the forge scaffolds ESL-flagged .esp by default [fact:plugin.hedr.installed]
- Light slots do not count against the 254 full slots; this install runs 115 full and 437 light plugins [fact:load_order.installed]
- Check before flagging: `f4forge plugin esl-check <p>` (reports LIGHT-ELIGIBLE, below-floor or above-max IDs) [fact:plugin.light_range]
- Too many new records (more than the range holds): split the plugin or keep it full [fact:plugin.light_range]
