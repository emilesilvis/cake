---
name: cake-doctor
description: Check the health of the Cake system without changing it. Use when auditing Cake, detecting consequences of manually added or moved cards or issues, validating Cakes, Slices, visibly marked Cupcakes, navigation, Plate links, and cross-links, checking visible WIP limits and Rhythms, or deciding which repair skill should take over. Route portfolio membership and priority judgment to cake-prioritise and Slice or Cupcake repair to cake-slice.
---

# Cake Doctor

Read `../../CONTEXT.md` completely before acting. Trello is the portfolio interface and Plate is the source of truth for currentness. A Slice lives in GitHub when its Cake names a repository and in Trello otherwise. A Cupcake is one parentless Trello card identified by the visible `🧁` title marker wherever it currently lives. Diagnose current state; do not create a parallel tracking system.

## Workflow

1. Run `python3 scripts/doctor.py check`. This is read-only. Treat a visible legacy `Slice index:` field as a finding even when the underlying links are otherwise correct. If configuration or a provider is unavailable, report that plainly and stop only where the missing source prevents a reliable conclusion.
2. Lead with either `Cake is healthy` or `Cake needs attention`. Give the current counts and visible WIP position, then list only actionable findings using card names and clickable links. Do not dump raw issue codes or JSON unless the user asks.
3. Separate structural health from portfolio judgment. A structurally valid Plate is not automatically the right Plate. If the user added or moved current work manually, or the report marks a portfolio challenge as required, read `../cake-prioritise/SKILL.md` completely and challenge whether the Slice and its parent or the standalone Cupcake belong in current WIP.
4. Route classification, membership, Cake Stand, Next Slice, Plate, and WIP decisions to `cake-prioritise`. A parentless unmarked card is a finding until classified: one bounded standalone outcome may become a Cupcake; several or follow-on outcomes need a Cake and Slice; recurrence needs a Rhythm; an atomic action belongs as a Task. Route malformed Slice or Cupcake contracts, `🧁` marking, Previous or Available slices drift, and provider migration to `cake-slice`. Read the delegated skill completely before using it.
5. Do not repair anything during the check. Any repair must use the responsible skill's exact preview and wait for explicit approval before writing.
6. Re-run the check after approved repairs. Call the system healthy only when structural findings are gone; mention any provider check that could not be completed.

## What healthy means

- Every Slice lives in one valid place selected by its Cake. Every Cake on the Stand shows its Current Slice or its Next Slice; a Parked Cake shows its derived Previous Slice when prior work exists; and every Cake shows exactly every valid inactive Slice under Available slices. Exhaustive terminal history stays out of sight.
- Every current Slice has one Plate entry in Eating or Blocked, one finishable Outcome and observable Success, and exactly one parent Cake on the Stand. A GitHub Slice and its Plate card link to each other; a Trello-only Slice uses its own card directly.
- Every Cupcake has the visible `🧁` title marker, one finishable Outcome and observable Success once it reaches the Stand or Plate, and no parent Cake. A Cupcake may live in Pantry, Cake Stand, or Plate; the same Trello card moves whole among them and keeps its ordinary Task checklist. It never appears in a Cake's Current, Previous, Next, or Available Slice links or in the Slice catalog.
- Every Cake being eaten links to exactly its current Plate cards. Every waiting Cake has one valid canonical Next Slice. Parent and Plate links use clickable Trello short URLs; canonical GitHub Slice links use issue URLs.
- Archived Slices may point to archived historical Cakes. Archived Cakes do not appear in normal portfolio choices and are never treated as active membership.
- Visible `/N` suffixes are respected. Cake Stand limits count active Cakes and waiting Cupcakes. The Eating limit covers all current Plate work, including Blocked Slices and Cupcakes. A separate Blocked suffix, if present, is also checked.
- Rhythm cards have Cadence, Load, and Supports, but do not consume Cake Stand or Plate WIP. They may have one Cake-managed current-period checklist and one `Cake history` checklist of weekly completed/target summaries.

## Human-interface rule

Never add health cards, audit comments, arbitrary timestamps, migration notes, origin fields, UUIDs, or provenance labels to Trello. The managed dated entries in a Rhythm's `Cake history` checklist are domain results, not audit metadata. Do not retain a card merely to explain history. Use the existing human contracts, normal lists, clickable links, and Trello's own archive. A diagnosis may contain technical detail internally, but the user-facing report should read like a thoughtful board review.

## Helper

Run from this skill directory:

```bash
python3 scripts/doctor.py check
```
