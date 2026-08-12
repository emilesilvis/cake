---
name: cake-doctor
description: Check the health of the Trello-first Cake system without changing it. Use when auditing Cake, checking whether Trello is healthy, detecting consequences of manually added or moved cards, validating Cake–Slice and GitHub cross-links, checking visible WIP limits and Capacity Constraints, or deciding which repair skill should take over. Route portfolio membership and priority judgment to cake-prioritise and Slice definition or delivery-link repair to cake-slice.
---

# Cake Doctor

Read `../../CONTEXT.md` completely before acting. Trello is the human interface and source of truth. Diagnose current state; do not create a parallel tracking system.

## Workflow

1. Run `python3 scripts/doctor.py check`. This is read-only. If configuration or a provider is unavailable, report that plainly and stop only where the missing source prevents a reliable conclusion.
2. Lead with either `Cake is healthy` or `Cake needs attention`. Give the current counts and visible WIP position, then list only actionable findings using card names and clickable links. Do not dump raw issue codes or JSON unless the user asks.
3. Separate structural health from portfolio judgment. A structurally valid Plate is not automatically the right Plate. If the user added or moved current work manually, or the report marks a portfolio challenge as required, read `../cake-prioritise/SKILL.md` completely and challenge whether the Slice and its parent belong in current WIP.
4. Route membership, Cake Stand, Next Slice, Plate, and WIP decisions to `cake-prioritise`. Route malformed Slice contracts and reciprocal GitHub delivery links to `cake-slice`. Read the delegated skill completely before using it.
5. Do not repair anything during the check. Any repair must use the responsible skill's exact preview and wait for explicit approval before writing.
6. Re-run the check after approved repairs. Call the system healthy only when structural findings are gone; mention any provider check that could not be completed.

## What healthy means

- Every current Slice is an open canonical Plate card in Eating or Blocked, has one finishable Outcome and observable Success, and points to exactly one Cake on the Stand.
- Every Cake being eaten links to exactly the Slices currently on Plate. Every waiting Cake has one valid Next Slice. All Cake–Slice links are clickable Trello short URLs.
- Archived Slices may point to archived historical Cakes. Archived Cakes do not appear in normal portfolio choices and are never treated as active membership.
- Visible `/N` suffixes are respected. The Eating limit covers all current Plate work, including Blocked Slices. A separate Blocked suffix, if present, is also checked.
- Capacity Constraint cards have Cadence, Load, and Supports, but do not consume Cake Stand or Plate WIP.
- A Trello `GitHub issue:` link, when present, has a reciprocal `Cake Slice:` link in that issue.

## Human-interface rule

Never add health cards, audit comments, timestamps, migration notes, origin fields, UUIDs, or provenance labels to Trello. Do not retain a card merely to explain history. Use the existing human contracts, normal lists, clickable links, and Trello's own archive. A diagnosis may contain technical detail internally, but the user-facing report should read like a thoughtful board review.

## Helper

Run from this skill directory:

```bash
python3 scripts/doctor.py check
```

Use `--without-delivery-links` only when GitHub is deliberately out of scope or unavailable. Say explicitly that reciprocal delivery links were not checked.
