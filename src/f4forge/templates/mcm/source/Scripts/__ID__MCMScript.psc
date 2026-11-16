ScriptName __ID__MCMScript extends Quest
{Reads __NAME__'s MCM settings and reacts when the player changes them.}

bool Property Enabled = true Auto Hidden
float Property Strength = 1.0 Auto Hidden

Event OnQuestInit()
    RegisterForExternalEvent("OnMCMSettingChange|__ID__", "OnMCMSettingChange")
    LoadSettings()
EndEvent

Function LoadSettings()
    Enabled = MCM.GetModSettingBool("__ID__", "bEnabled:Main")
    Strength = MCM.GetModSettingFloat("__ID__", "fStrength:Main")
EndFunction

Function OnMCMSettingChange(string modName, string id)
    If modName == "__ID__"
        LoadSettings()
    EndIf
EndFunction

Function Toggle()
    Enabled = !Enabled
    MCM.SetModSettingBool("__ID__", "bEnabled:Main", Enabled)
    Debug.Notification("__NAME__ " + Enabled)
EndFunction
