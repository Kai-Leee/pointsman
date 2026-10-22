---
name: pointsman
description: Split a multi-file coding task into a checked plan, show its placement, order, estimated time and cost, then run workers that follow the current session agent. Use when the user asks to run a task with Pointsman or Jev routing, or asks for a task plan with time and cost estimates.
---

# Pointsman

The session agent stays in charge. Jev chooses among candidates; the plan tool checks the result; workers do the edits.

## 1. Workers follow the session agent

Workers inherit this session's model, permissions, tools and the user's CLAUDE.md. Do not give workers a restricted agent type and do not strip project instructions. The only per-task settings are the model and effort from the task's profile:

| profile | model | effort |
|---|---|---|
| `claude_opus55_medium` | opus | medium |
| `claude_sonnet55_medium` | sonnet | medium |
| `claude_haiku55_low` | haiku | low |

A profile the session cannot use falls back to the session's own model.

## 2. Build the plan

Propose up to five candidate decompositions yourself, then ask Jev to choose with the `jev-ai` MCP `decide` tool. Write the chosen plan to `.pointsman/plan.json`:

```json
{ "requirements": ["R1", "R2"],
  "tasks": [{ "id": "n1", "profile": "claude_sonnet55_medium", "writes": ["pkg/a.py"],
              "inputs": [], "outputs": ["A"], "requirements": ["R1"] }] }
```

A task that needs another task's result lists that result in `inputs`; the producer lists it in `outputs`. Two tasks never write the same file.

Limit: this path calls Jev through the plain `decide` tool. Budget ledger, token admission and fixed question contracts from the research runner are not applied yet.

## 3. Check before any worker starts

```sh
node "${CLAUDE_PLUGIN_ROOT}/bin/pointsman-plan.mjs" --plan .pointsman/plan.json --repo . --html .pointsman/plan.html
```

- Exit 2 means a placement error (`PLAN_WRITE_OVERLAP`, `PLAN_INPUT_WITHOUT_PRODUCER`, `PLAN_DUPLICATE_PRODUCER`, `PLAN_CYCLE`, `PLAN_REQUIREMENT_UNOWNED`). Fix the plan and run the check again.
- `gaps.links` lists imports between tasks that the plan does not order. Add the missing input/output pair, or say why the order does not matter.
- `coupling` covers tasks that import each other, where adding links would create a cycle:
  - `split_file_cycles`: files that import each other sit in different tasks. Move them into one task before starting.
  - `task_cycles` with `resolves_with_foundation_first` and `foundation_share` at most 0.5: put `foundation_files` in a first task that the others depend on.
  - Other `task_cycles`: keep the plan, and give every worker in the group the `foundation_files` names and signatures from the spec as fixed interfaces.
- `estimate` gives time and cost per task from recorded runs. They are medians of a small sample. Present them as estimates.
- If `skip.skip` is true, do the task directly in this session without decomposition.

Show `.pointsman/plan.html` to the user, as an artifact when the session can publish one, before workers start.

## 4. Run the workers

Run the tasks in `validation.order`, at most `--slots` at a time, with the Workflow tool when the user invoked this skill. Each worker gets its task id, its files, the requirements it owns and the inputs it can rely on. Then run the project's own tests.

## 5. Close out

Rerun the plan check with the run's results. Report the `feedback` list: plan errors, missing links, size outliers, failed checks and files that a review changed. Repairs are not automated in this version. Hand the list to the user and let them decide the next step.
