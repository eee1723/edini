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

### General skills

- `grill-me` — Interview the user relentlessly about a plan or design until reaching shared understanding.
- `recipe-library` — Reuse before authoring. Query a library of human-built subnet recipes (pre-validated node networks) and rebuild them deterministically with parameter overrides, instead of hand-authoring nodes. Captures new subnets from the scene to grow the library.

> **Note:** The procedural-modeling pipeline skills (`procedural-modeling`,
> `edini-brainstorm`, `recipe-authoring`, `component-building`,
> `assembly-wiring`, `verification`, `parametric-testing`) and their backing
> tools (`build_procedural_asset`, `validate_recipe`, `rebuild_component`,
> `houdini_variant_scatter`) have been **disabled** and moved to
> `_disabled_backup/procedural-modeling/`. The general geometry workflow
> (sandbox, commit_sandbox, verify_asset, orientation/health/inventory
> checks) remains available. To restore, see the NOTE block in
> `python3.11libs/edini/tool_executor.py`.
