<p align="center">
  <img src="assets/cake-logo.png" alt="A cheerful layer cake on a stand beside one plated slice" width="260">
</p>

# Cake

Cake is a tiny personal portfolio system for people with more interesting things to do than unlimited capacity allows.

It separates the directions you care about from the outcomes you are actually working on:

| Place | What goes there | In ordinary language |
| --- | --- | --- |
| **Pantry** | Possible Cakes | “Maybe later.” |
| **Cake Stand** | Active Cakes | “This matters now.” |
| **Plate** | Current Slices | “I am finishing this.” |
| **Rhythms** | Recurring practices | “This keeps coming back.” |

A **Cake** is an enduring direction. A **Slice** is one finishable outcome. A **Rhythm** is recurring load such as gym, study, piano, or reviews.

The useful rule is simple: if it can be finished once, it is probably a Slice. If it returns next week wearing the same hat, it is probably a Rhythm.

The precise vocabulary lives in [CONTEXT.md](CONTEXT.md).

## Three helpful utensils

- **cake-prioritise** decides what deserves your attention and safely moves Cakes and Slices.
- **cake-slice** shapes one direction into a small, independently finishable Slice.
- **cake-doctor** checks that the whole system still makes sense without changing anything.

Clone the whole repository, then link or copy the directories under `skills/` into your agent's skills directory. The skills share the code in `cake_core/`, so they like to stay together.

## Set the table

Cake uses Trello as its human-facing portfolio:

- **Pantry** holds possible Cakes.
- **Cake Stand** has `On the stand /N`, `Parked`, and `Finished` lists. It may also have a `Rhythms` list.
- **Plate** has `Eating /N` and `Blocked` lists. Plate is the source of truth for current work.

The `/N` suffix is the visible WIP limit. It is a guardrail, not an electrified fence.

Configure the boards once:

```bash
cd skills/cake-prioritise
python3 scripts/portfolio.py config set \
  --pantry-board 'Pantry' \
  --cake-stand-board 'Cake Stand' \
  --plate-board 'Plate' \
  --timezone 'Europe/Amsterdam' \
  --priority 'The change that matters most now'
```

Configuration is stored at `~/.config/cake/config.json`. Trello credentials live at `~/.trello/credentials`:

```text
API_KEY=...
API_TOKEN=...
```

Slices live in Trello by default. If a Cake names a GitHub repository, its unfinished Slices live in GitHub issues instead; Plate shows a small linked card while a Slice is current.

## Card recipes

A Cake needs a direction:

```text
Direction: What this Cake is trying to change
Finished when: Optional genuine ending
Repository: Optional https://github.com/<owner>/<repository>
```

A Slice needs one result and one way to know it is done:

```text
Cake: https://trello.com/c/<parent>
Outcome: One independently finishable result
Success: One observable test
Not included: Optional useful boundary
Disposition: Candidate
```

Cake manages the Current, Previous, Next, Available, and Plate links. You should not have to do link gardening by hand.

A Rhythm stays deliberately small:

```text
Cadence: When it recurs
Load: How much attention it consumes
Supports: The continuing benefit
```

Every Rhythm is reviewed on a Monday–Sunday week. A daily habit can stay pleasantly plain:

```text
Cadence: Daily
Load: Complete the habit every day
Supports: The continuing benefit
```

That automatically produces a Monday–Sunday checklist. You can check all the boxes together at the end of the week.

Cake reads checked boxes directly and keeps no separate occurrence history.

## Roll the Rhythms

Preview the next checklist update:

```bash
python3 skills/cake-prioritise/scripts/portfolio.py rhythms sync
```

If the preview looks right, apply its approval token:

```bash
python3 skills/cake-prioritise/scripts/portfolio.py rhythms sync \
  --apply-token '<token from the preview>'
```

Rollover is never automatic. Cake reuses the managed checklist for the new period and resets completed boxes only after approval. Monday can wait a moment; it is used to this.

## Safety, because frosting gets slippery

Every state-changing helper previews its exact Trello or GitHub changes first. Approval is tied to the state that was observed, so stale plans stop instead of improvising.

Cake does not create audit cards, hidden status systems, UUID links, or surprise migrations. The boards remain the interface, and archived records remain history rather than clutter.

For the full lifecycle rules, see [CONTEXT.md](CONTEXT.md). The provider decision is recorded in [ADR 0001](docs/adr/0001-provider-aware-slice-records.md).

## Development

The rules and provider adapters live in `cake_core/`; the skill scripts are thin command-line wrappers.

```bash
python3 -m unittest discover -s tests -v
```
