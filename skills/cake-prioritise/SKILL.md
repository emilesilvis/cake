---
name: cake-prioritise
description: Compare viable Slices across the whole Cake portfolio, challenge current commitments, distinguish recurring Rhythms from Cakes and Slices, recommend the single best next focus, and safely preview/apply Cake Stand, Next Slice, or Plate transitions. Use when deciding what to eat next, reviewing active work, classifying habits or routines, nominating a Next Slice, entering or exiting Plate, or resolving WIP overage. Delegate canonical Slice shaping to cake-slice.
---

# Cake Prioritise

Read `../../CONTEXT.md` completely before acting. Choose focus in the context of the whole portfolio; never calculate a numeric priority score.

## Workflow

1. Run `python3 scripts/portfolio.py config get`. If Pantry, Cake Stand, or Plate is missing, ask for the new board reference and configure it. Do not migrate old cards as part of this skill.
2. State the persisted portfolio priority and confirm or replace it every run. A conversational replacement lasts for this run unless the user asks to save it.
3. Run `rhythms sync` before `snapshot`. If the Rhythm checklists are not current, inspect the exact preview, summarize the affected Rhythms, and wait for explicit approval before repeating it with `--apply-token`. Never apply a rollover implicitly. Then run `snapshot`; it reads every Cake's full Slice history as well as Plate and each configured Rhythm's current-period checklist. Treat Plate and Cake Stand order as advisory claims to challenge. Consider serious Pantry challengers as well as every Cake on the Stand, including all Slices shown as available to eat.
4. Resolve current WIP limits from their provider. A suffix such as `On the stand /3` or `Eating /2` is an explicit list limit; also inspect Trello List Limits with available browser access and include configured Rhythms and conversational constraints. Blocked Slices remain on Plate and count. If a limit cannot be observed, say so rather than inventing it.
5. For every quantified Rhythm, read `progress`: report completed and remaining load for its exact daily or Monday–Sunday period. Each checked item in the current Cake-managed checklist is one completed occurrence. `needs_sync` means the checklist has not yet been prepared or reconciled for that period; do not infer completion elsewhere.
6. Fail closed only when unavailable data is relevant to the decision or transition. Surface external drift. Repair only Cake-managed Rhythm checklists through the separately approved `rhythms sync`; never rewrite unrelated checklists. If a serious contender has stale or insufficient context, ask instead of rejecting it for poor card maintenance.
7. Normalize one valid Slice for each serious contender. Read `../cake-slice/SKILL.md` and use its quality gates. Resolve candidates from every Slice available to eat, not only from Plate. If the winner needs a new or reshaped Slice, complete that separately through `cake-slice`, then re-read the portfolio.
8. Compare the viable shortlist with explicit pairwise trade-offs. Apply hard consequences, viability, portfolio movement, then opportunity cost against the remaining recurring load. Name one winner and what waits, and include completed and remaining recurring load when it materially affects the choice. If Cake Stand or Plate exceeds its limit, give the complete keep/park or keep/pause set.
9. Build one coherent transition plan. Preview it with the helper, present it using the approval format below, and wait for explicit approval.
10. Apply the identical plan with its confirmation token. If portfolio state or a Rhythm checklist changed, preview again. Capacity overage never hard-blocks, but pass `--allow-capacity-overage` only after the user explicitly accepts the reviewed overage.

If a current Plate card was added before its parent Cake existed, repair it in three separately approved writes: use `create-cake` to put the mature parent in Pantry, use `cake-slice adopt` to attach and shape the parentless card, then preview and apply `move_cake` to admit the parent to the Stand. Do not create a duplicate Cake, reparent an owned Slice, or combine unseen writes under one approval.

## State rules

- Pantry contains possible, still-ill-defined Cakes. Cake Stand contains only Cakes. Admission to Cake Stand is an explicit commitment with Direction and either a valid Next Slice or a current Slice.
- Every Cake card shows `Current slices:` while it is being eaten, one derived `Previous slice:` while Parked when prior work exists, or one `Next slice:` while it waits on the Stand, plus `Available slices:` for every valid inactive Slice that could be eaten later. Current, Previous, and Next are mutually exclusive. Current and Next stay out of Available; a Paused Previous Slice may also be Available because history and eligibility are distinct. Finished and Abandoned Slices stay out of Available. Exhaustive history remains internal.
- A Cake with any Plate entry is **Being Eaten** and `Current slices:` must link to every current Plate card with stable `https://trello.com/c/<shortLink>` URLs. A Cake on the Stand without one is **Waiting on the Stand** and must have exactly one valid `Next slice:` link. Plate membership remains authoritative.
- Every canonical Slice has a reciprocal `Cake:` link to its parent in stable Trello URL form. A current GitHub Slice also has a reciprocal Plate Projection: the issue uses `Plate:` and the Trello card uses `Slice:`. Never store a UUID as a cross-link. Every membership transition must update all affected links before it is complete.
- Only the nominated Next Slice may be pulled. `cake-prioritise` may replace that nomination whenever priorities change. Nominating moves the chosen Slice out of Available and returns any replaced Next Slice to Available. Pulling replaces Next with Current. To add another current Slice for the same Cake, nominate and pull it in the same plan.
- Plate is solely the source of truth for current WIP. A Trello-only Slice reopens its canonical card in Eating or Blocked. A GitHub-backed Slice creates a Plate Projection there. Finish, Pause, or Abandon removes the Plate entry; Abandon requires a reason. Paused GitHub issues remain open, while Finished and Abandoned issues close.
- A recurring occurrence that becomes due again substantially unchanged is a Rhythm, not a Slice. Keep one persistent Rhythm card with Cadence, Load, and Supports; do not generate daily or weekly Plate cards. Cake manages one checklist named `Cake · <current period>` on that card. Each item is one occurrence. Current-period sync preserves checked boxes; an approved new-period rollover reuses the checklist and resets them. A bounded effort to establish or materially change the Rhythm may still be a Cake and Slice.
- A configured Rhythms list may share the Cake Stand Trello board, but its cards are not Cake Stand members and do not consume Cake Stand or Plate WIP. Always include their load when judging what fits.
- Exiting a Slice removes its Cake-side Current Slice link. When the last current Slice exits, nominate another Slice or Park/Finish the parent Cake in the same plan. Parking records that exiting Slice as `Previous slice:`; finishing the Cake keeps history off its card. A Cake cannot leave the Stand while one of its Slices remains on Plate.
- Parked and Finished Cakes live alongside the active Cake Stand list but are not active membership. A Parked Cake has no Current or Next Slice; it may show one derived Previous Slice and any valid inactive Slices under Available. Parked is only for a still-valid Cake that may return. When a former Cake was superseded or reclassified and should no longer be a portfolio option, archive its card after every current Slice has exited; archived Cakes remain historical link targets only.
- Keep Trello portfolio-facing. Do not create retirement lists, audit comments, UUID links, origin fields, or parallel status metadata. Use normal Cake, Slice, Projection, and Rhythm contracts with clickable links and provider-native archive or issue state.
- Limits strongly discourage overage and require explicit review; they do not mechanically block it.

## Decision output

Lead with:

```text
Eat [Cake]: [Slice] next because [decisive reason]. Keep [Cakes]. Park or wait on [Cakes].
```

Then include only the closest challengers, meaningful viability failures, and the opportunity cost needed to trust the choice.

## Approval output

Ask for approval as one short, natural-language question:

```text
Approve: <what will happen to the linked Cakes and Slices, and where>?
```

Lead immediately with `Approve:` and link entity names instead of printing bare URLs. Speak only in the Cake metaphor: put or finish Slices on the Plate; put Cakes on, take them off, or park them from the Stand; move possible Cakes into or out of the Pantry. Do not expose helper operations, field names, links, providers, confirmation tokens, or terms such as `Slice Registry`, `canonical record`, `Disposition`, or `Plate Projection`.

Add at most one short follow-up sentence when the user needs a capacity warning, a non-obvious consequence, or clarity that nearby work is excluded. Keep it conversational; never add `Changes:`, `Result:`, or `Excluded:` sections, and never narrate an execution log. The approved natural-language outcome remains bound to the helper's exact preview and confirmation token internally.

For example:

```text
Approve: finish [Slice] on the Plate and take [Cake] off the Stand to park it? The Stand and Plate will both be 5/5; [Other Slice] remains available to eat later.
```

For Rhythm checklist maintenance, use the same concise approval style, for example: `Approve: prepare this week's occurrence checklists for Gym and Piano, resetting last week's completed boxes?`

## Transition helper

Run from this skill directory. A transition plan is JSON with `operations` and optional session-only `capacity_policies`.

```bash
python3 scripts/portfolio.py config get
python3 scripts/portfolio.py rhythms sync
python3 scripts/portfolio.py rhythms sync --apply-token '<token>'
python3 scripts/portfolio.py snapshot
python3 scripts/portfolio.py create-cake \
  --name '<Cake>' \
  --direction '<direction>' \
  --pantry-list '<Pantry list>' \
  --repository '<optional GitHub owner/repository>'
python3 scripts/portfolio.py preview --plan @/path/to/plan.json
python3 scripts/portfolio.py apply --plan @/path/to/plan.json \
  --confirmation-token '<token>'
```

Run `create-cake` once without `--apply-token` to preview it, then repeat the identical command with `--apply-token '<token>'` after approval.

Configure new boards without migrating cards:

```bash
python3 scripts/portfolio.py config set \
  --pantry-board '<board>' \
  --cake-stand-board '<board>' \
  --plate-board '<board>' \
  --timezone '<IANA timezone>' \
  --priority '<current portfolio priority>'
```

Operations are:

- `{"action":"nominate","cake":"<ref>","slice":"<ref>"}`
- `{"action":"pull","cake":"<ref>","lane":"eating|blocked"}`
- `{"action":"exit","plate_slice":"<ref>","disposition":"finished|paused|abandoned","reason":"<required for abandoned>","next_slice":"<ref>"}` or use `"cake_state":"parked|finished"`
- `{"action":"move_cake","cake":"<ref>","to":"on_stand|parked|finished",...Cake contract fields}`
- `{"action":"archive_cake","cake":"<ref>"}` for a Parked Cake that is no longer a valid portfolio option
- `{"action":"reorder","collection":"on_stand|eating|blocked","record":"<ref>","position":0}`

Use `cake-slice` for canonical Slice writes. Use this helper—not direct Trello edits—for membership, nomination, exits, and order.

When correcting a recurrence-only Slice, preview an `exit` with disposition `abandoned` and a precise reclassification reason. Move its parent to Parked while the replacement is being established unless the Cake genuinely Finished or has another valid outcome Slice. Preview the persistent Rhythm card separately before writing it. Once the replacement is healthy and the former Cake is no longer a valid option, preview `archive_cake`; do not leave a relic in Parked merely to preserve history.
