---
name: cake-slice
description: Shape one chosen Cake direction into an independently finishable canonical Slice and, after explicit approval, create or update its Trello card on Plate. Optionally maintain a reciprocal GitHub delivery-issue link. Use when work is vague, unending, too broad, checklist-shaped, or needs a concise Outcome/Success boundary. Do not compare Cakes, nominate Next Slice, or change Cake Stand or Plate membership; use cake-prioritise for those decisions.
---

# Cake Slice

Read `../../CONTEXT.md` completely before acting. Produce exactly one bounded Slice with exactly one parent Cake.

## Workflow

1. Resolve one parent Cake with `python3 scripts/slice.py read-cake --cake '<stable-id-or-url>'`. Discover available facts before asking questions. If there is no stable parent Cake, shape a conversational draft but do not write it.
2. Confirm one chosen direction. If choosing between Cakes or directions is the real problem, stop and use `cake-prioritise`.
3. Read an existing canonical Slice with `read-slice` when reshaping it. Every Slice is a Trello card on Plate; there are no proxies or alternate canonical records.
4. Shape one candidate internally and repair every failed quality gate before presenting it. Ask one material decision question at a time, with a recommendation.
5. Create or update the canonical Slice card on Plate. A new candidate starts archived; `cake-prioritise` controls whether it is current.
6. A GitHub issue is an optional Delivery Link, not a prerequisite or canonical Slice. Only link an issue that already represents delivery of the same outcome. When linked, include `GitHub issue:` on Trello and maintain `Cake Slice:` in the GitHub issue body so navigation works both ways.
7. Run `create` or `update` without an apply token. Show the exact returned write and wait for explicit approval.
8. Re-run the identical command with `--apply-token '<confirmation-token>'`. A stale token requires a fresh preview and approval. If a linked GitHub issue changed, preview the reciprocal-link write again.
9. Return the canonical Slice URL to `cake-prioritise`. Do not nominate it or make it current.

## Quality gates

A Slice must have one coherent Outcome, be independently finishable, have observable Success, advance its Cake's Direction, and include only infrastructure needed for that outcome. Add `Not included` only to resolve meaningful ambiguity. Never use an implementation checklist as the Slice contract.

Uncertainty reduction can be a valid Outcome when it resolves a named risk and has observable Success.

## Canonical contract

The title is `[Cake]: [Slice]`. The canonical body is:

```text
Cake: https://trello.com/c/<stable-parent-short-link>
Outcome: <one short sentence>
Success: <one short observable sentence>
Not included: <optional essential boundary>
GitHub issue: <optional GitHub delivery issue URL>
Disposition: Candidate
```

The `Cake:` value is always a clickable Trello short URL, never a UUID. Plate is the sole canonical registry. A candidate, paused, finished, or abandoned Slice is an archived Plate card. A current Slice is an open card in `Eating` or `Blocked`. Never create a Slice only in GitHub or on Cake Stand.

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

Add `--github-issue 'https://github.com/<owner>/<repo>/issues/<number>'` only for an optional reciprocal Delivery Link. Add `--apply-token '<token>'` only after approval. If a provider is unavailable, still give the exact draft and say that nothing was written.
