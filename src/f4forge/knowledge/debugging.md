# Debugging

- `f4forge logs` summarises f4se.log, plugin logs, the Papyrus log and crash logs [fact:crash.logs]
- F4SE loader statuses (no version data, address library needs update, incompatible...) are explained [fact:f4se.loader_statuses]
- `f4forge explain "<error text>"` matches known signatures [fact:f4se.loader_statuses]
- Papyrus logging needs [Papyrus] bEnableLogging=1 in Fallout4Custom.ini [fact:crash.logs]
- Crash logs: Addictol Crash Logger (installed) writes to My Games/Fallout4/F4SE unless its toml says otherwise [fact:crash.logs]
- After a new crash: stop, roll back the last change, isolate the smallest one [fact:crash.logs]
- Check the runtime first: `f4forge game` [fact:runtime.version.installed]
