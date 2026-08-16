<p align="center">
  <img src="assets/cake-logo.png" alt="A cheerful layer cake on a stand beside one plated slice" width="260">
</p>

# Cake

Cake is a small personal portfolio system. It separates enduring things you care about from the bounded outcomes you are actually focusing on.

| Place | Contains | Meaning |
| --- | --- | --- |
| **Pantry** | Cakes | Things that might deserve commitment one day |
| **Cake Stand** | Cakes | Your capacity-limited active portfolio |
| **Plate** | Current Slices | The bounded outcomes consuming attention now |

**Capacity Constraints** describe recurring commitments that reduce available attention. They are planning inputs, not a fourth place or portfolio members, and do not consume Cake Stand or Plate WIP. A Trello setup may keep their cards in an auxiliary `Rhythms / capacity` list.

A Cake can sit on the Cake Stand without being actively eaten: it is active but waiting, and must name one **Next Slice**. A Slice lives in a GitHub issue when its Cake names a repository; otherwise it lives in a Trello card. Plate contains only current work. If any of a Cake's Slices is current, the Cake must be on the Stand.

The full, deliberately small vocabulary lives in [CONTEXT.md](CONTEXT.md).

## Three skills

- **cake-prioritise** compares the whole portfolio, recommends one focus, and manages Cake Stand, Next Slice, and Plate transitions.
- **cake-slice** turns one chosen direction into a single independently finishable Slice with observable success.
- **cake-doctor** checks the Trello system without changing it, explains inconsistencies in human terms, and routes repairs to the responsible skill.

`cake-prioritise` decides *which Slice deserves focus*. `cake-slice` defines *what finishing that Slice means*.
`cake-doctor` checks whether the resulting system is coherent; structural health never substitutes for prioritisation.

Clone the whole repository so all three skills can use the shared `cake_core` module, then link or copy the directories under `skills/` into your agent's skills directory.

## Trello topology

Pantry, Cake Stand, and Plate are configurable Trello boards:

- Pantry contains only Cakes that are not yet active.
- The Cake Stand board holds Cakes across `On the stand`, `Parked`, and `Finished`; only `On the stand` is active portfolio membership. The board may also host an auxiliary `Rhythms / capacity` list whose cards are planning inputs, not Cake Stand members.
- Plate is the source of truth for current work. It is not a backlog or a list of every Slice.

Parked is for a still-valid Cake that may return. A superseded or misclassified Cake card may instead be archived after all of its Slices have left current Plate work. Archived Cake cards are read only to keep historical Slice parent links valid; they stay out of normal portfolio views and choices.

Suggested Trello list names show their WIP limits directly:

- Cake Stand board: `On the stand /3`, `Parked`, `Finished`; optionally, an auxiliary `Rhythms / capacity` list
- Plate: `Eating /2`, `Blocked`

The configuration accepts stable Trello list IDs, so display names and WIP suffixes may change without breaking the tooling.

If a Slice was added to Plate before its Cake existed, repair it in this order: create the Cake in Pantry, attach the Slice to it, then move the Cake onto the Stand. Cake previews each change before writing it.

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

A mature Cake keeps this short, human-facing contract on its card:

```text
Direction: What this Cake is trying to change
Finished when: Optional genuine ending
Repository: Optional https://github.com/<owner>/<repository>
Current slices: https://trello.com/c/<stable-short-link>
- https://trello.com/c/<another-stable-short-link>
Previous slice: <canonical Trello card or GitHub issue URL>
Next slice: <canonical Trello card or GitHub issue URL>
Available slices: <canonical Trello card or GitHub issue URL>
- <another Slice available to eat>
```

`Current slices` appears only while the Cake is being eaten and points to its Plate cards. `Previous slice` appears only while the Cake is Parked and points to the most recent Slice whose exit parked it. It is derived historical navigation, never a current commitment or candidate. `Next slice` appears only while the Cake is waiting on the Stand. Current, Previous, and Next are mutually exclusive. `Available slices` lists every valid inactive Slice that could be eaten later; Current, Next, Finished, and Abandoned Slices do not appear there. A paused Previous Slice may also appear under Available because its historical and eligibility roles are distinct. Exhaustive history remains derived internally and stays off the Cake card. Plate membership remains authoritative for currentness.

`Repository` selects where the Cake's nonterminal Slices live. Attaching a Repository is safe only when no unfinished Trello Slice remains; Finished and Abandoned Trello Slices stay where they ended and may remain the Parked Cake's Previous Slice.

A Slice contains:

```text
Cake: https://trello.com/c/<stable-parent-short-link>
Outcome: One independently finishable result
Success: One observable test
Not included: Optional essential boundary
Plate: Optional current Plate projection URL
Disposition: Candidate
```

`Cake:` is always a clickable Trello short URL, never a UUID. For a repository-backed Cake, this body lives in a GitHub issue labelled `cake-slice`; `Plate:` appears only while that issue is current. For a Trello-only Cake, the body lives on the canonical Trello Slice card and `Plate:` is omitted.

A current GitHub-backed Slice has a small Plate projection:

```text
Slice: https://github.com/<owner>/<repository>/issues/<number>
Cake: https://trello.com/c/<stable-parent-short-link>
Disposition: Current
```

The issue's `Plate:` link and the projection's `Slice:` link are reciprocal. On Pause, Finish, or Abandon, the projection is archived and the issue loses its Plate link. Paused issues stay open; Finished and Abandoned issues close. A Trello-only Slice simply reopens or archives its canonical card.

A Capacity Constraint may use this lightweight card contract:

```text
Cadence: When it recurs
Load: How much attention it normally consumes
Supports: The continuing benefit or Cake it supports
```

Completing one occurrence of a Capacity Constraint does not create a Slice; it simply recurs. A bounded effort to establish or materially change the rhythm may still be a Cake with finishable Slices.

Trello is intentionally the portfolio interface. A Cake's Slices live in GitHub when it names a repository and in Trello otherwise. The helpers do not add health cards, audit comments, timestamps, UUID cross-links, or parallel status metadata. They use visible lists, short contracts, clickable links, and native archives or issue state.

All state-changing helpers preview exact transitions first and bind approval to the observed source state. WIP limits strongly discourage over-commitment, but an explicitly reviewed overage can proceed.

## Development

The reusable rules and provider adapters live in `cake_core/`; the skill scripts are thin command-line interfaces over that shared module.

```bash
python3 -m unittest discover -s tests -v
```

The decision about where Slices live is recorded in [ADR 0001](docs/adr/0001-provider-aware-slice-records.md).
