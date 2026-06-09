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

(none — add skills as needed)
