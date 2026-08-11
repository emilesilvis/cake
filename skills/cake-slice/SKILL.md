---
name: cake-slice
description: Shape one chosen Cake direction into an independently finishable canonical Slice and, after explicit approval, create or update that Slice in its configured GitHub or Plate-native source. Use when work is vague, unending, too broad, checklist-shaped, or needs a concise Outcome/Success boundary. Do not compare Cakes, nominate Next Slice, or change Cake Stand or Plate membership; use cake-prioritise for those decisions.
---

# Cake Slice

Read `../../CONTEXT.md` completely before acting. Produce exactly one bounded Slice with exactly one parent Cake.

## Workflow

1. Resolve one parent Cake with `python3 scripts/slice.py read-cake --cake '<stable-id-or-url>'`. Discover available facts before asking questions. If there is no stable parent Cake, shape a conversational draft but do not write it.
2. Confirm one chosen direction. If choosing between Cakes or directions is the real problem, stop and use `cake-prioritise`.
3. Read an existing canonical Slice with `read-slice` when reshaping it. Never edit a Plate proxy as though it were canonical.
4. Shape one candidate internally and repair every failed quality gate before presenting it. Ask one material decision question at a time, with a recommendation.
5. Use the Cake's stored Slice source. For a Pantry Cake without one, accept the source selected by `cake-prioritise` via `--slice-source`; do not update the Cake yourself.
6. Before creating a GitHub Slice, inspect the repository's existing open and closed issues—not only issues matching the configured Slice query or label. If an issue already represents the outcome, do not create another one: surface it and decide whether to adopt/update it or shape a genuinely distinct Slice. The helper also fails closed on likely lexical duplicates, but that guard does not replace this semantic review.
7. Run `create` or `update` without an apply token. Show the exact returned write and wait for explicit approval.
8. Re-run the identical command with `--apply-token '<confirmation-token>'`. A stale token requires a fresh preview and approval; the duplicate check runs again immediately before any GitHub create.
9. Return the canonical Slice URL or ID to `cake-prioritise`. Do not nominate it or put it on Plate.

## Quality gates

A Slice must have one coherent Outcome, be independently finishable, have observable Success, advance its Cake's Direction, and include only infrastructure needed for that outcome. Add `Not included` only to resolve meaningful ambiguity. Never use an implementation checklist as the Slice contract.

Uncertainty reduction can be a valid Outcome when it resolves a named risk and has observable Success.

## Canonical contract

The title is `[Cake]: [Slice]`. The canonical body is:

```text
Cake: <stable Cake URL or ID>
Outcome: <one short sentence>
Success: <one short observable sentence>
Not included: <optional essential boundary>
Disposition: Candidate
```

Current membership is derived from Plate, not copied into an editable second definition. A Plate-native candidate is an archived card; a GitHub Slice gets a lightweight Plate proxy only when `cake-prioritise` pulls it.

## Helper

Run commands from this skill directory.

```bash
python3 scripts/slice.py read-cake --cake '<cake>'
python3 scripts/slice.py read-slice --cake '<cake>' --slice '<canonical-slice>'

python3 scripts/slice.py create \
  --cake '<cake>' \
  --title '<Cake>: <Slice>' \
  --outcome '<outcome>' \
  --success '<success>' \
  --not-included '<boundary>'

python3 scripts/slice.py update \
  --cake '<cake>' \
  --slice '<canonical-slice>' \
  --title '<Cake>: <Slice>' \
  --outcome '<outcome>' \
  --success '<success>'
```

Add `--slice-source 'plate'` or a configured GitHub query only when the Cake does not store one yet. Add `--apply-token '<token>'` only after approval. If a provider is unavailable, still give the exact draft and say that nothing was written.
