<p align="center">
  <img src="assets/cake-logo.png" alt="A cheerful layer cake on a stand beside one plated slice" width="260">
</p>

# Cake

Cake is a small personal portfolio system. It separates enduring things you care about from the bounded outcomes you are actually focusing on.

| Place | Contains | Meaning |
| --- | --- | --- |
| **Pantry** | Cakes | Things that might deserve commitment one day |
| **Cake Stand** | Cakes | Your capacity-limited active portfolio |
| **Plate** | Slices | The outcomes you are pursuing right now |

A Cake can sit on the Cake Stand without being on your Plate: it is active, but waiting, and must name one **Next Slice**. If any of its Slices is on Plate, the Cake must be on the Stand. Plate is the only source of truth for current work.

The full, deliberately small vocabulary lives in [CONTEXT.md](CONTEXT.md).

## Two skills

- **cake-prioritise** compares the whole portfolio, recommends one focus, and manages Cake Stand, Next Slice, and Plate transitions.
- **cake-slice** turns one chosen direction into a single independently finishable Slice with observable success.

`cake-prioritise` decides *which Slice deserves focus*. `cake-slice` defines *what finishing that Slice means*.

Clone the whole repository so both skills can use the shared `cake_core` module, then link or copy the two directories under `skills/` into your agent's skills directory.

## Sources are configurable

Pantry, Cake Stand, and Plate can have different providers. The current adapter uses Trello for those three roles. Each Cake stores its own Slice source, currently either:

- `plate` — canonical Slice cards live archived or current on Plate; or
- `github:owner/repository?query=label%3Acake-slice` — canonical Slices are GitHub issues selected by a query.

Suggested Trello lists are:

- Cake Stand: `On the stand`, `Parked`, `Finished`
- Plate: `Eating`, `Blocked`

Configure brand-new boards without migrating anything:

```bash
cd skills/cake-prioritise
python3 scripts/portfolio.py config set \
  --pantry-board 'Pantry' \
  --cake-stand-board 'Cake Stand' \
  --plate-board 'Plate' \
  --priority 'The change that matters most now'
```

Configuration is stored at `~/.config/cake/config.json`. Trello credentials are read from `~/.trello/credentials` as `API_KEY=...` and `API_TOKEN=...`; GitHub access uses an authenticated `gh` CLI.

## Card contracts

A mature Cake keeps this short contract on its card:

```text
Direction: What this Cake is trying to change
Finished when: Optional genuine ending
Slice source: plate or a GitHub issue query
Next slice: One canonical Slice URL or ID, only while waiting
```

Current Slice links are derived from Plate and are never written into the Cake card.

A canonical Slice contains:

```text
Cake: Stable parent Cake URL or ID
Outcome: One independently finishable result
Success: One observable test
Not included: Optional essential boundary
Disposition: Candidate
```

All state-changing helpers preview exact transitions first and bind approval to the observed source state. WIP limits strongly discourage over-commitment, but an explicitly reviewed overage can proceed.

## Development

The reusable rules and provider adapters live in `cake_core/`; the two skill scripts are thin command-line interfaces over that shared module.

```bash
python3 -m unittest discover -s tests -v
```
