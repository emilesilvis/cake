<p align="center">
  <img src="assets/cake-logo.png" alt="A cheerful layer cake on a stand beside one plated slice" width="260">
</p>

# Cake

Cake is a small personal portfolio system. It separates enduring things you care about from the bounded outcomes you are actually focusing on.

| Place | Contains | Meaning |
| --- | --- | --- |
| **Pantry** | Cakes | Things that might deserve commitment one day |
| **Cake Stand** | Cakes | Your capacity-limited active portfolio |
| **Plate** | Slices | Every bounded outcome, current or archived |

A Cake can sit on the Cake Stand without being actively eaten: it is active but waiting, and must name one **Next Slice**. Every Slice has exactly one canonical Trello card on Plate. Open cards in `Eating` or `Blocked` are current; archived cards are candidates, paused work, or completed history. If any of a Cake's Slices is current, the Cake must be on the Stand.

The full, deliberately small vocabulary lives in [CONTEXT.md](CONTEXT.md).

## Two skills

- **cake-prioritise** compares the whole portfolio, recommends one focus, and manages Cake Stand, Next Slice, and Plate transitions.
- **cake-slice** turns one chosen direction into a single independently finishable Slice with observable success.

`cake-prioritise` decides *which Slice deserves focus*. `cake-slice` defines *what finishing that Slice means*.

Clone the whole repository so both skills can use the shared `cake_core` module, then link or copy the two directories under `skills/` into your agent's skills directory.

## Trello topology

Pantry, Cake Stand, and Plate are configurable Trello boards:

- Pantry contains only Cakes that are not yet active.
- Cake Stand contains only Cakes, including active, parked, and finished Cakes.
- Plate is the sole canonical Slice registry and source of truth for current work.

Suggested Trello list names show their WIP limits directly:

- Cake Stand: `On the stand /3`, `Parked`, `Finished`
- Plate: `Eating /2`, `Blocked`

The configuration accepts stable Trello list IDs, so display names and WIP suffixes may change without breaking the tooling.

Configure brand-new boards without migrating anything:

```bash
cd skills/cake-prioritise
python3 scripts/portfolio.py config set \
  --pantry-board 'Pantry' \
  --cake-stand-board 'Cake Stand' \
  --plate-board 'Plate' \
  --priority 'The change that matters most now'
```

Configuration is stored at `~/.config/cake/config.json`. Trello credentials are read from `~/.trello/credentials` as `API_KEY=...` and `API_TOKEN=...`.

## Card contracts

A mature Cake keeps this short contract on its card:

```text
Direction: What this Cake is trying to change
Finished when: Optional genuine ending
Next slice: One canonical Slice URL or ID, only while waiting
```

Current Slice links are derived from Plate and are never written into the Cake card.

A canonical Slice contains:

```text
Cake: Stable parent Cake URL or ID
Outcome: One independently finishable result
Success: One observable test
Not included: Optional essential boundary
GitHub issue: Optional delivery issue URL
Disposition: Candidate
```

When a Slice has a GitHub delivery issue, the Trello card links to it with `GitHub issue:` and the GitHub issue links back with `Cake Slice:`. Trello remains canonical; a GitHub issue is never a second Slice record. GitHub access requires an authenticated `gh` CLI only when such a link is used.

All state-changing helpers preview exact transitions first and bind approval to the observed source state. WIP limits strongly discourage over-commitment, but an explicitly reviewed overage can proceed.

## Development

The reusable rules and provider adapters live in `cake_core/`; the two skill scripts are thin command-line interfaces over that shared module.

```bash
python3 -m unittest discover -s tests -v
```
