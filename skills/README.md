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
- `recipe-authoring` — Writing valid procedural asset Recipes. Param three-state system, anchor design, pre-flight checklist (A1-A6).
- `component-building` — Building individual components with `build_component`. Backend red lines, VEX rules, template usage, repair discipline.
- `assembly-wiring` — Assembling verified components. Anchor mounting, CTP configuration, postprocess chains, Workspace fallback.
- `verification` — Two-layer verification protocol (health + orientation + inventory), debug discipline.
- `parametric-testing` — Parameter boundary testing before commit. Test scenarios, intersection detection, constraint verification.

### Utility skills

- `grill-me` — Interview the user relentlessly about a plan or design until reaching shared understanding.
