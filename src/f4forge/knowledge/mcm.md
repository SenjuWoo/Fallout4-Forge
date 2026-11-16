# MCM (Mod Configuration Menu)

- Files: MCM/Config/<modName>/config.json, settings.ini (defaults), keybinds.json [fact:mcm.schema]
- Top level: modName, displayName, minMcmVersion, pluginRequirements, content or pages [fact:mcm.schema]
- ModSetting* controls need id "name:Section" with a default in settings.ini [fact:mcm.schema]
- GlobalValue and PropertyValue* need sourceForm "Plugin.esp|FormID" [fact:mcm.schema]
- Hotkeys need a keybinds.json entry with the same id and an action (CallFunction, CallGlobalFunction, ...) [fact:mcm.schema]
- Script side: MCM.GetModSettingBool/Int/Float/String; listen with RegisterForExternalEvent("OnMCMSettingChange|<modName>", ...) [fact:mcm.schema]
- Never ship MCM/Settings/<modName>.ini: MCM writes user values there [fact:mcm.schema]
- Validate: `f4forge mcm <folder>`; 41 of 44 installed configs pass and 3 have real defects [fact:mcm.installed_check]
- Requirement: MCM, Nexus fallout4/mods/21497 [fact:frameworks.installed]
