# Edini Skills

This directory holds skills that Edini loads into the Pi agent.
The global Pi skill loading is disabled (`--no-skills`); only skills
placed here are available.

## How to add a skill

### Option A: A single markdown file

Drop a `.md` file at the root of this directory. Pi treats each
root-level `.md` as an independent skill.

```
skills/
  my-skill.md
```

### Option B: A skill directory with SKILL.md

Create a subdirectory containing a `SKILL.md`:

```
skills/
  my-skill/
    SKILL.md
    reference.md       # optional supporting files
    scripts/           # optional helper scripts
```

`SKILL.md` must include a YAML front matter with `name` and `description`:

```markdown
---
name: my-skill
description: What this skill does and when to trigger it.
---

# My Skill

Instructions for the agent...
```

## Current skills

### Pipeline skills (in workflow order)

- `edini-brainstorm` — Design router for Houdini procedural asset creation. Ask clarifying questions, decompose components, produce design spec.
- `procedural-modeling` — Lightweight pipeline router. Determines which phase you're in and loads the correct specialized skill.
- `recipe-authoring` — Writing valid procedural asset Recipes. Param three-state system, anchor design, pre-flight checklist (A1-A9).
- `component-building` — Diagnosing build_procedural_asset failures and fixing the recipe. Backend red lines, VEX rules, template usage, error-code triage (A8/A9/cook/G2), repair discipline.
- `assembly-wiring` — Reference for designing anchors, Copy-to-Points layout, and variant scatter in a recipe (assembly itself is automatic inside build_procedural_asset).
- `verification` — Verification protocol (health + orientation + inventory), G3 commit gate, verification_receipt reporting rules, debug discipline.
- `parametric-testing` — Parameter boundary testing before commit. Test scenarios, intersection detection, constraint verification.

### Utility skills

- `grill-me` — Interview the user relentlessly about a plan or design until reaching shared understanding.
