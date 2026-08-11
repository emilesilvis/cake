---
name: cake-prioritise
description: Compare viable Slices across the whole Cake portfolio, challenge current commitments, recommend the single best next focus, and safely preview/apply Cake Stand, Next Slice, or Plate transitions. Use when deciding what to eat next, reviewing active work, nominating a Next Slice, entering or exiting Plate, or resolving WIP overage. Delegate canonical Slice shaping to cake-slice.
---

# Cake Prioritise

Read `../../CONTEXT.md` completely before acting. Choose focus in the context of the whole portfolio; never calculate a numeric priority score.

## Workflow

1. Run `python3 scripts/portfolio.py config get`. If Pantry, Cake Stand, or Plate is missing, ask for the new board reference and configure it. Do not migrate old cards as part of this skill.
2. State the persisted portfolio priority and confirm or replace it every run. A conversational replacement lasts for this run unless the user asks to save it.
3. Run `snapshot`. Treat Plate and Cake Stand order as advisory claims to challenge. Consider serious Pantry challengers as well as every Cake on the Stand.
4. Resolve current WIP limits from their provider. Inspect Trello List Limits with available browser access; include configured capacity records and conversational constraints. Blocked Slices remain on Plate and count. If a limit cannot be observed, say so rather than inventing it.
5. Fail closed only when unavailable data is relevant to the decision or transition. Surface external drift; never auto-sync it. If a serious contender has stale or insufficient context, ask instead of rejecting it for poor card maintenance.
6. Normalize one valid Slice for each serious contender. Read `../cake-slice/SKILL.md` and use its quality gates. If the winner needs a new or reshaped canonical Slice, complete that separately through `cake-slice`, then re-read the portfolio.
7. Compare the viable shortlist with explicit pairwise trade-offs. Apply hard consequences, viability, portfolio movement, then opportunity cost. Name one winner and what waits. If Cake Stand or Plate exceeds its limit, give the complete keep/park or keep/pause set.
8. Build one coherent transition plan. Preview it with the helper, show the exact operations, resulting state, and any strong capacity warning, then wait for explicit approval.
9. Apply the identical plan with its confirmation token. If state changed, preview again. Capacity overage never hard-blocks, but pass `--allow-capacity-overage` only after the user explicitly accepts the reviewed overage.

## State rules

- Pantry contains possible, still-ill-defined Cakes. Admission to Cake Stand is an explicit commitment with Direction, Slice source, and either a valid Next Slice or a current Slice.
- A Cake with any Plate Slice is **Being Eaten**. A Cake on the Stand without one is **Waiting on the Stand** and must have exactly one valid Next Slice.
- Only the nominated Next Slice may be pulled. `cake-prioritise` may replace that nomination whenever priorities change. Pulling clears the pointer. To add another current Slice for the same Cake, nominate and pull it in the same plan.
- Plate is the sole source of truth for current WIP and has only Eating and Blocked. Finish, Pause, or Abandon removes a Slice; Abandon requires a reason.
- When the last current Slice exits, nominate another Slice or Park/Finish the parent Cake in the same plan. A Cake cannot leave the Stand while one of its Slices remains on Plate.
- Parked and Finished Cakes live alongside the active Cake Stand list but are not active membership. A stable habit may Finish as a Cake and continue as a capacity constraint.
- Limits strongly discourage overage and require explicit review; they do not mechanically block it.

## Decision output

Lead with:

```text
Eat [Cake]: [Slice] next because [decisive reason]. Keep [Cakes]. Park or wait on [Cakes].
```

Then include only the closest challengers, meaningful viability failures, and the opportunity cost needed to trust the choice.

## Transition helper

Run from this skill directory. A plan is JSON with `operations` and optional session-only `capacity_policies`.

```bash
python3 scripts/portfolio.py config get
python3 scripts/portfolio.py snapshot
python3 scripts/portfolio.py preview --plan @/path/to/plan.json
python3 scripts/portfolio.py apply --plan @/path/to/plan.json \
  --confirmation-token '<token>'
```

Configure new boards without migrating cards:

```bash
python3 scripts/portfolio.py config set \
  --pantry-board '<board>' \
  --cake-stand-board '<board>' \
  --plate-board '<board>' \
  --priority '<current portfolio priority>'
```

Operations are:

- `{"action":"nominate","cake":"<ref>","slice":"<ref>"}`
- `{"action":"pull","cake":"<ref>","lane":"eating|blocked"}`
- `{"action":"exit","plate_slice":"<ref>","disposition":"finished|paused|abandoned","reason":"<required for abandoned>","next_slice":"<ref>"}` or use `"cake_state":"parked|finished"`
- `{"action":"move_cake","cake":"<ref>","to":"on_stand|parked|finished",...Cake contract fields}`
- `{"action":"reorder","collection":"on_stand|eating|blocked","record":"<ref>","position":0}`

Use `cake-slice` for canonical Slice writes. Use this helper—not direct Trello edits—for membership, nomination, exits, and order.
