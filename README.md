<p align="center">
  <img src="assets/cake-logo.png" alt="A cheerful layer cake on a stand beside one plated slice" width="260">
</p>

# Cake

Cake is a tiny personal portfolio system for people with more interesting things to do than unlimited capacity allows.

It separates the directions you care about from the outcomes you are actually working on:

| Place | What goes there | In ordinary language |
| --- | --- | --- |
| **Pantry** | Possible Cakes and Cupcakes | “Maybe later.” |
| **Cake Stand** | Active Cakes and waiting Cupcakes | “This matters now.” |
| **Plate** | Current Slices and Cupcakes | “I am finishing this.” |
| **Rhythms** | Recurring practices | “This keeps coming back.” |

A **Cake** is an enduring direction. A **Slice** is one finishable outcome belonging to a Cake. A **Cupcake** is a standalone finishable outcome with no parent Cake. A **Rhythm** is recurring load such as gym, study, piano, or reviews.

The useful rule is simple: several outcomes form a Cake; one outcome on its own is a Cupcake; an action inside either is a Task. If it returns next week wearing the same hat, it is probably a Rhythm.

The precise vocabulary lives in [CONTEXT.md](CONTEXT.md).

## Three helpful utensils

- **cake-prioritise** decides what deserves your attention and safely moves Cakes, Slices, and Cupcakes.
- **cake-slice** shapes independently finishable Slices and Cupcakes.
- **cake-doctor** checks that the whole system still makes sense without changing anything.

Clone the whole repository, then link or copy the directories under `skills/` into your agent's skills directory. The skills share the code in `cake_core/`, so they like to stay together.

## Set the table

Cake uses Trello as its human-facing portfolio:

- **Pantry** holds possible Cakes and Cupcakes.
- **Cake Stand** has `On the stand /N`, `Parked`, and `Finished` lists. Cakes stay there while their Slices are eaten; waiting or parked Cupcakes keep their whole card there until they return to the Plate. It may also have a `Rhythms` list.
- **Plate** has `Eating /N` and `Blocked` lists. Plate is the source of truth for current Slices and Cupcakes.

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

A Cupcake uses the same outcome boundary without a parent:

```text
Title: 🧁 File the tax return
Outcome: The tax return is filed
Success: The tax authority confirms receipt
Not included: Optional useful boundary
Disposition: Candidate
```

The `🧁` title prefix is the visible type marker. You may add it yourself, or Cake may classify an existing card as one standalone outcome and propose marking it after explicit approval:

```bash
python3 skills/cake-slice/scripts/slice.py cupcake \
  --card 'https://trello.com/c/<card>' \
  --title 'File the tax return' \
  --outcome 'The tax return is filed' \
  --success 'The tax authority confirms receipt'
```

That command previews the marking first. Repeat it with the returned `--apply-token` only after approving the classification.

The same Cupcake card moves from Pantry to Cake Stand to Plate, so its ordinary Trello checklist moves with it. Checklist items are Tasks and remain user-managed; Cake does not mistake the checklist for the Cupcake's completion contract. Pausing returns the Cupcake to the Stand, while finishing or abandoning archives it. If follow-on outcomes emerge, promote it into a Cake and make the current outcome its first Slice.

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

Cake reads checked boxes directly. On rollover it adds one compact result such as
`2026-08-10–2026-08-16 · 2/4` to the card's `Cake history` checklist, so later
reviews can compare weeks without retaining another full daily checklist.

## Roll the Rhythms

Preview the next checklist update:

```bash
python3 skills/cake-prioritise/scripts/portfolio.py rhythms sync
```

On Sunday, preview a specific coming Monday without rolling the current week early:

```bash
python3 skills/cake-prioritise/scripts/portfolio.py rhythms sync \
  --week-start '2026-08-17'
```

If the preview looks right, apply its approval token:

```bash
python3 skills/cake-prioritise/scripts/portfolio.py rhythms sync \
  --week-start '2026-08-17' \
  --apply-token '<token from the preview>'
```

Rollover is never automatic. After approval, Cake records the completed/target result in `Cake history`, reuses the managed checklist for the new period, and resets its completed boxes. Monday can wait a moment; it is used to this.

## Safety, because frosting gets slippery

Every state-changing helper previews its exact Trello or GitHub changes first. Approval is tied to the state that was observed, so stale plans stop instead of improvising.

Cake does not create audit cards, hidden status systems, UUID links, or surprise migrations. The boards remain the interface, and archived records remain history rather than clutter.

For the full lifecycle rules, see [CONTEXT.md](CONTEXT.md). The provider decision is recorded in [ADR 0001](docs/adr/0001-provider-aware-slice-records.md), and the portable visible Cupcake model in [ADR 0002](docs/adr/0002-portable-marked-cupcakes.md).

## Development

The rules and provider adapters live in `cake_core/`; the skill scripts are thin command-line wrappers.

```bash
python3 -m unittest discover -s tests -v
```
