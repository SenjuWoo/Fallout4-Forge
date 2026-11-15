# Workspace ownership

- Project root: `.` (this file's directory; one owner shared by every agent).
- Active source: `src/f4forge/` (package, knowledge data, templates), `workers/`, `skills/`, `tests/`. Nothing is built yet: PLAN.md is the work order, STATE.md the progress record.
- Versioning: Git on `main`, tags `vX.Y.Z`; the version lives in `src/f4forge/__init__.py`.
- Repository: public GitHub repository `Fallout4-Forge` (MIT), requested by the owner; created by the publish tasks in PLAN.md, not before.
- Publication intent: public once the local release gate passes; releases are cut from a tag after CI passes on that commit.
- Private files: `LOCAL.md` (machine paths and installed facts) is git-ignored and never published.
- Explicit GitHub publication: public and MIT for original work by default, subject to rights/platform terms; preserve existing licences. Mods made with the forge publish to their usual destination (Nexus Mods); a mod needing no compilation gets no duplicate source hosting by default.
- Existing-repository maintenance: preserve its remote/visibility and follow the requested update, documentation, push and release scope.
- Read-only inputs: the installed game and its Data, mod-manager staging, saves, INIs, other forges, downloaded tools and supplied references.
- Release staging: separate runtime payload from source, ownership notes, STATE/PLAN/validation, changelogs, logs and backups. Keep required licences.
- Recovery: read STATE.md and version/build/run metadata before continuing; keep the last known-good artifact.
