---
name: cake-slice
description: Turn a chosen project direction into one independently finishable slice and, after explicit approval, update an existing Trello card or create a new one from a Git repository. Use when work is vague, unending, too broad, framed as an implementation checklist, or needs a short Outcome/Success card. Do not use to compare priorities across projects; use cake-prioritise for that.
---

# Cake Slice

Produce one bounded outcome. Keep the card short. Ask only about decisions that materially change its outcome or boundary.

## Workflow

1. Identify the input mode.
   - **Trello card:** run `python3 scripts/cake_trello.py read-card <card-url-or-id>` and treat its current contents as the source direction.
   - **Repository:** inspect the repository, its current state, and its Git remote. Run `python3 scripts/cake_trello.py config get --repo <path>` before preparing a new card.
2. Establish one chosen direction.
   - If the user supplied one, use it.
   - Otherwise infer one candidate from the available context, recommend it, and wait for confirmation before slicing.
3. Discover facts from the environment. Do not ask the user for information available in the card, repository, Git history, or configuration.
4. Shape one candidate slice. Explore alternatives internally. Surface alternatives only when a genuine trade-off requires the user's decision.
5. Apply every quality gate below. Repair a failed candidate before presenting it.
6. Present the exact Trello draft and wait for explicit approval.
7. After approval, use the helper's preview token to apply the same draft. Never perform a Trello write before approval.

Ask decision questions one at a time. Include a recommended answer with each question.

## Quality gates

A slice must:

- express one coherent outcome;
- be independently finishable, without requiring another unfinished slice;
- have observable success criteria;
- advance the chosen direction;
- include only the infrastructure needed for this outcome; and
- omit implementation steps and checklists.

A slice may deliver usable value, reduce uncertainty, or do both. Pure technical enablement qualifies only when it independently resolves a named risk or uncertainty.

## Card contract

Use this exact shape:

```text
Title: [Project]: [Slice]

Outcome: [one short sentence]
Success: [one short observable sentence]
Not included: [one essential boundary, only when omission creates real ambiguity]
```

Keep the project name and slice title scannable. Never add an implementation checklist.

## Trello operations

Use `scripts/cake_trello.py` for deterministic reads, configuration, previews, and writes. Run it relative to this skill directory.

### Update an input card

Preview without writing:

```bash
python3 scripts/cake_trello.py update-card \
  --card '<url-or-id>' \
  --title '<Project>: <Slice>' \
  --outcome '<outcome>' \
  --success '<success>' \
  --not-included '<boundary>'
```

Show the returned draft to the user. After approval, repeat the command with `--apply-token '<token>'`. The helper preserves the previous card title and description in a Trello comment before changing the card.

### Create a card from a repository

First resolve the persisted destination:

```bash
python3 scripts/cake_trello.py config get --repo '<repo-path>'
```

If no destination exists, ask for the board and list, then persist them:

```bash
python3 scripts/cake_trello.py config set --repo '<repo-path>' --board '<board>' --list '<list>'
```

Preview a new card:

```bash
python3 scripts/cake_trello.py create-card \
  --repo '<repo-path>' \
  --title '<Project>: <Slice>' \
  --outcome '<outcome>' \
  --success '<success>' \
  --not-included '<boundary>'
```

After approval, repeat the command with `--apply-token '<token>'`.

If Trello or destination configuration is unavailable, still produce the exact draft. Explain the missing dependency and do not claim the card was written.
