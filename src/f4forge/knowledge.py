"""Knowledge base and routing: facts with tiers, topics, frameworks, and `plan` for a request."""
from __future__ import annotations

import re

from .util import KNOWLEDGE_DIR, ForgeError, load_json

TIERS = ("installed", "primary", "secondary", "unverified")
FACT_FIELDS = ("id", "claim", "tier", "source", "checked", "how")
DATA_FILES = ("facts.json", "frameworks.json", "routes.json", "errors.json", "SOURCES.json", "game.json")


def load(name: str):
    return load_json(KNOWLEDGE_DIR / name)


# --- facts ---------------------------------------------------------------------

def validate_facts(doc) -> list[str]:
    """Schema problems; an empty list means valid. A fact needs every field and a known tier."""
    errors = []
    if not isinstance(doc, dict) or not isinstance(doc.get("facts"), list):
        return ["facts.json must be an object with a 'facts' list"]
    seen = set()
    for i, f in enumerate(doc["facts"]):
        where = f.get("id") if isinstance(f, dict) and f.get("id") else f"#{i}"
        if not isinstance(f, dict):
            errors.append(f"{where}: not an object")
            continue
        for k in FACT_FIELDS:
            if not isinstance(f.get(k), str) or not f[k].strip():
                errors.append(f"{where}: missing {k}")
        if f.get("tier") and f["tier"] not in TIERS:
            errors.append(f"{where}: unknown tier {f['tier']!r} (one of {', '.join(TIERS)})")
        if f.get("tier") == "primary" and not re.search(r"https?://", str(f.get("source", ""))):
            errors.append(f"{where}: a primary fact names its URL in source")
        if f.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(f.get("id"))
    return errors


def fact_index() -> dict[str, dict]:
    return {f["id"]: f for f in load("facts.json")["facts"]}


def facts(query: str | None = None) -> dict:
    data = load("facts.json")["facts"]
    if not query:
        return {"count": len(data), "facts": [{"id": f["id"], "tier": f["tier"]} for f in data],
                "hint": "f4forge facts <query> prints matching facts in full"}
    q = query.lower()
    hits = [f for f in data if q in f["id"].lower() or q in f["claim"].lower()]
    if not hits:
        raise ForgeError(f"no fact matching '{query}'", "list ids with: f4forge facts")
    return {"query": query, "count": len(hits), "facts": hits}


# --- topics ----------------------------------------------------------------------

def topic_names_from_routes() -> list[str]:
    data = load("routes.json")
    names = list(data.get("topics", []))
    for r in data["routes"]:
        for t in r.get("knowledge", []):
            if t not in names:
                names.append(t)
    return names


def topics() -> list[dict]:
    files = {p.stem: p for p in KNOWLEDGE_DIR.glob("*.md")}
    out = []
    for name in sorted(set(files) | set(topic_names_from_routes())):
        p = files.get(name)
        title = name
        if p:
            title = next((ln.lstrip("# ").strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()), name)
        out.append({"topic": name, "title": title, "available": bool(p)})
    return out


def topic(name: str) -> dict:
    stem = name[:-3] if name.endswith(".md") else name
    p = KNOWLEDGE_DIR / f"{stem}.md"
    if not p.is_file():
        known = [t["topic"] for t in topics()]
        if stem in known:
            raise ForgeError(f"knowledge topic '{stem}' is planned but not written yet",
                             "read the related facts with: f4forge facts <word>")
        close = [t for t in known if stem.lower() in t or t in stem.lower()]
        raise ForgeError(f"no knowledge topic '{stem}'", "list topics with: f4forge knowledge" +
                         (f" (close: {', '.join(close)})" if close else ""))
    text = p.read_text(encoding="utf-8")
    cited = sorted(set(re.findall(r"\[fact:([a-z0-9_.\-]+)\]", text)))
    idx = fact_index()
    return {"topic": stem, "text": text, "facts_cited": cited,
            "facts_missing": [c for c in cited if c not in idx]}


# --- routing ----------------------------------------------------------------------

def _kw_regex(kw: str) -> re.Pattern:
    # Whole words or phrases, plural tolerated; lookarounds so "c++" and "won't" match too.
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw.lower()) + r"(?:s|es)?(?![a-z0-9])")


def score_routes(request: str) -> list[tuple[int, dict, list[str]]]:
    text = " ".join(request.lower().split())
    scored = []
    for r in load("routes.json")["routes"]:
        hits = [kw for kw in r["keywords"] if _kw_regex(kw).search(text)]
        score = sum(2 if " " in kw else 1 for kw in hits)
        if score:
            scored.append((score, r, hits))
    scored.sort(key=lambda x: -x[0])
    return scored


def plan(request: str, available_commands: set[str] | None = None, ck_tier: str | None = None) -> dict:
    data = load("routes.json")
    scored = score_routes(request)
    if not scored:
        return {"request": request, "matched": False, "routes": [], "principle": data["principle"],
                "always": data["always"], "hint": "no route matched; f4forge knowledge lists topics, "
                                                  "f4forge capabilities lists commands"}
    top = scored[0][0]
    chosen = [x for x in scored if x[0] >= max(2, top // 2)] or scored[:1]
    commands, topics_, tools, avoid, gaps = [], [], [], [], []
    for _, r, _ in chosen:
        for c in r["commands"]:
            if c not in [x["command"] for x in commands]:
                name = c.split()[1] if c.startswith("f4forge ") and len(c.split()) > 1 else None
                commands.append({"command": c, "available": (name in available_commands)
                                 if available_commands is not None and name else None})
        for t in r["knowledge"]:
            if t not in topics_:
                topics_.append(t)
        for t in r["tools"]:
            if t not in tools:
                tools.append(t)
        for a in r["avoid"]:
            if a not in avoid:
                avoid.append(a)
        if r.get("gap"):
            gaps.append({"route": r["id"], "gap": r["gap"]})
        if r.get("gap_without_creation_kit") and ck_tier != "creation-kit":
            gaps.append({"route": r["id"], "gap": r["gap_without_creation_kit"]})
    return {
        "request": request,
        "matched": True,
        "routes": [{"id": r["id"], "title": r["title"], "score": s, "matched": h} for s, r, h in chosen],
        "also_considered": [{"id": r["id"], "score": s} for s, r, _ in scored[len(chosen):len(chosen) + 3]],
        "commands": commands,
        "knowledge": topics_,
        "tools": tools,
        "tool_tiers": data["tool_tiers"],
        "creation_kit_tier": ck_tier,
        "avoid": avoid,
        "gaps": gaps,
        "principle": data["principle"],
        "always": data["always"],
    }


# --- payload health ------------------------------------------------------------------

def payload_problems() -> list[str]:
    problems = []
    loaded = {}
    for name in DATA_FILES:
        try:
            loaded[name] = load(name)
        except (OSError, ValueError) as e:
            problems.append(f"{name}: {e}")
    if "facts.json" in loaded:
        problems += [f"facts.json: {e}" for e in validate_facts(loaded["facts.json"])]
    if "facts.json" in loaded and "game.json" in loaded:
        ids = {f.get("id") for f in loaded["facts.json"].get("facts", [])}
        for k, v in loaded["game.json"].items():
            if isinstance(v, dict) and v.get("fact") and v["fact"] not in ids:
                problems.append(f"game.json {k}: cites unknown fact {v['fact']}")
    if "routes.json" in loaded:
        ids = [r.get("id") for r in loaded["routes.json"].get("routes", [])]
        if len(ids) != len(set(ids)):
            problems.append("routes.json: duplicate route id")
    return problems
