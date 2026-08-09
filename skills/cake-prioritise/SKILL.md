---
name: cake-prioritise
description: Compare viable project slices across the full portfolio and recommend the single most worthwhile slice to do next, including a complete keep/pause set when active work exceeds its limit. Use when deciding what to work on next, challenging Active or Next commitments, comparing projects or candidate slices, or asking for the highest-priority slice. Do not write the selected slice to Trello; hand the confirmed winner to cake-slice.
---

# Cake Prioritise

Choose one next slice in the context of the whole portfolio. Do not calculate a numeric priority score. Make the decisive trade-off explicit.

## Workflow

1. Run `python3 scripts/portfolio.py config get`.
   - If the portfolio boards are missing, ask for the Projects and Backlog board names, then persist them with `config set`.
   - Show the persisted portfolio priority and ask the user to confirm or replace it on every run.
   - Persist a replacement with `config set --priority '<priority>'`.
2. Run `python3 scripts/portfolio.py snapshot` to scan all open Projects and Backlog cards.
3. Resolve the Active work-in-progress limit.
   - Prefer the current value shown by Trello's List Limits plugin when browser or computer-use access is available.
   - Otherwise ask once. Do not silently treat a stored or previously observed value as current.
4. Treat `Tasks` and `Fixed time slots/habit` as capacity constraints, not candidates. Exclude `Done` and `Failed/Parked` work.
5. Treat Active and Next as claims to challenge, not as evidence that work deserves priority. Consider every remaining project and backlog card.
6. Create one normalized candidate slice for each plausible contender. Apply the `cake-slice` quality gates internally: one coherent outcome, independently finishable, observable, and aligned with its project direction.
7. Pause and ask if a serious contender has stale or insufficient context. Do not reject it because its card is poorly maintained.
8. Exclude candidates that fail viability. State which gate failed and why. Group obvious exclusions; explain plausible failures individually.
9. Compare the viable shortlist through explicit pairwise trade-offs. End with one winner.
10. If Active exceeds its limit, recommend the complete keep/pause set before naming the next slice.
11. After the user confirms the winner, read `../cake-slice/SKILL.md` and follow its workflow. Require a separate confirmation for the exact Trello draft.

Ask decision questions one at a time. Include a recommended answer with each question.

## Decision order

Apply these in order:

1. **Hard constraints:** honor genuine external commitments with consequences. Treat ordinary self-imposed due dates as trade-offs, not hard constraints.
2. **Viability:** require an independently finishable, observable slice that advances both its project direction and the portfolio priority.
3. **Portfolio movement:** prefer the slice that most advances the confirmed portfolio priority, considering effort, uncertainty, and what it unlocks.
4. **Opportunity cost:** name what must pause or wait. Choosing work without stopping anything is not prioritisation.

Do not use a weighted formula. Numbers imply precision the evidence rarely supports.

## Output contract

Lead with one short decision paragraph:

```text
Do [Project]: [Slice] next because [decisive reason]. Keep [projects]. Pause [projects].
```

Then add only the audit detail needed to trust the decision:

- closest challengers and why they lost;
- individual fit-for-purpose failures for plausible candidates; and
- grouped reasons for obvious exclusions.

Make no Trello changes. The confirmed winner belongs to `cake-slice`.

## Portfolio helper

Use `scripts/portfolio.py` relative to this skill directory.

```bash
# Read setup and the current persisted priority
python3 scripts/portfolio.py config get

# Configure or update any supplied value
python3 scripts/portfolio.py config set \
  --projects-board 'Projects' \
  --backlog-board 'Backlog' \
  --priority '<one-sentence current portfolio priority>'

# Collect a read-only portfolio snapshot
python3 scripts/portfolio.py snapshot
```

The helper performs read-only Trello calls. It never moves, edits, creates, archives, or deletes cards.
