# Cake

Cake is a personal portfolio system for deciding which enduring pursuits deserve attention and which bounded outcomes are being pursued now.

## Language

**Cake**:
A portfolio-level pursuit or direction that can yield one or more Slices. Its Trello card shows what is Current or Next while active, what was Previous while parked, and every other Slice still available to eat.
_Avoid_: Project, task, initiative

**Slice**:
One independently finishable outcome with observable success and exactly one parent Cake. A nonterminal Slice lives in a GitHub issue when its Cake names a Repository and otherwise in a Trello card; terminal history remains where it ended if its Cake later adopts a Repository.
_Avoid_: Task, implementation step, entire Cake

**Pantry**:
The collection of possible Cakes that have not been admitted to the active portfolio. Pantry Cakes may still be vague, incomplete, or merely aspirational.
_Avoid_: Backlog, queue

**Cake Stand**:
The capacity-limited active portfolio of mature Cakes. It contains only Cakes, each admitted as an explicit commitment with a clear Direction and either current work or a valid Next Slice.
_Avoid_: Projects board, project list, Slice list

**Plate**:
The capacity-limited view and authority for current Slices. A Trello Slice sits there directly; a GitHub Slice uses a small linked Trello card while it is current. Inactive Slices do not occupy it.
_Avoid_: Backlog, next queue

**Next Slice**:
The single validated Slice linked by a waiting Cake as its next pull-ready candidate. It is mutually exclusive with Current Slices.
_Avoid_: Current Slice, slice queue

**Previous Slice**:
The most recent Slice to leave the Plate when its Cake was parked. It is derived historical context, not a current commitment or a candidate to eat.
_Avoid_: Next Slice, Available Slice, Slice history

**Available Slice**:
A valid inactive Slice that could be eaten later. It is neither Current nor Next, and a Finished or Abandoned Slice is not available.
_Avoid_: Slice history, Current Slice, Next Slice

**Cake–Slice Link**:
The stable link from a Slice to its parent Cake together with the Cake's Current, Previous, Next, and Available Slice navigation. These links expose relationships but never decide currentness.
_Avoid_: UUID, copied status, alternate source of truth

**Being Eaten**:
The derived condition of a Cake that has at least one Slice on Plate. It is never stored as an independent status.
_Avoid_: Active label, in-progress Cake state

**Waiting on the Stand**:
A Cake Stand Cake with no Slice on Plate and exactly one valid Next Slice.
_Avoid_: Paused, inactive

**Parked**:
A mature, still-valid Cake deliberately removed from the active portfolio while remaining available for a future return.
_Avoid_: Pantry, Failed, Paused Slice

**Finished**:
A Cake whose intended change or Direction has genuinely ended. Finishing a Cake does not imply that every resulting routine or interest ceases.
_Avoid_: Parked, archived

**Paused Slice**:
A Slice removed from Plate while remaining available for its Cake to eat later.
_Avoid_: Parked Cake, Blocked Slice

**Blocked Slice**:
A current Slice that cannot presently advance but still belongs on Plate and consumes Plate capacity.
_Avoid_: Paused Slice

**Abandoned Slice**:
A Slice deliberately ended without claiming its Success condition was met, because it became unnecessary, invalid, or superseded.
_Avoid_: Finished Slice, Paused Slice

**Rhythm**:
A recurring practice, appointment, or obligation that consumes capacity without independently creating a lasting portfolio outcome. It can support a Cake without becoming a Cake or Slice, and its current-period progress is visible through recurring checklist items.
_Avoid_: Capacity Constraint, Habit Cake, recurring Slice, routine Slice

**Task**:
An execution action inside a Slice. A Task does not independently occupy Pantry, Cake Stand, or Plate.
_Avoid_: Slice, Cake
