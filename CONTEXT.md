# Cake

Cake is a personal portfolio system for deciding which enduring pursuits deserve attention and which bounded outcomes are being pursued now.

## Language

**Cake**:
A portfolio-level pursuit or direction that can yield one or more Slices. Its Trello card is the durable directory for the pursuit and all of its Slices.
_Avoid_: Project, task, initiative

**Slice**:
One independently finishable outcome with observable success, exactly one parent Cake, and exactly one canonical Slice Record.
_Avoid_: Task, implementation step, entire Cake

**Slice Record**:
The authoritative record of a Slice. It is a GitHub issue for a repository-backed Cake and a Trello card for a Trello-only Cake.
_Avoid_: Plate card, proxy, duplicate record

**Slice Registry**:
The complete set of canonical Slice Records belonging to one Cake. A Cake has one registry provider, chosen by whether it names a Repository.
_Avoid_: Plate, task backlog, current work

**Slice Index**:
The exhaustive list of canonical Slice Records on a Cake card. It is derived navigation, not an ordering or currentness signal.
_Avoid_: Next Slice, roadmap, Plate

**Plate Projection**:
The Trello card that makes one current GitHub-backed Slice visible on Plate. It links reciprocally to its canonical Slice Record and exists only while that Slice is current.
_Avoid_: Canonical Slice, copy, delivery issue

**Pantry**:
The collection of possible Cakes that have not been admitted to the active portfolio. Pantry Cakes may still be vague, incomplete, or merely aspirational.
_Avoid_: Backlog, queue

**Cake Stand**:
The capacity-limited active portfolio of mature Cakes. It contains only Cakes, each admitted as an explicit commitment with a clear Direction and either current work or a valid Next Slice.
_Avoid_: Projects board, project list, Slice list

**Plate**:
The capacity-limited view and authority for current Slices. It contains only current Trello canonical Slice cards or current Plate Projections; inactive Slices do not occupy it.
_Avoid_: Slice Registry, backlog, next queue

**Next Slice**:
The single validated canonical Slice Record linked by a waiting Cake as its next pull-ready candidate. It is mutually exclusive with Current Slices.
_Avoid_: Current Slice, slice queue

**Cake–Slice Link**:
The stable link from a Slice Record to its parent Cake together with the Cake's derived Slice Index, Current Slices, and Next Slice navigation. These links expose relationships but never decide currentness.
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
A Slice removed from Plate while remaining available for future nomination in its Slice Registry.
_Avoid_: Parked Cake, Blocked Slice

**Blocked Slice**:
A current Slice that cannot presently advance but still belongs on Plate and consumes Plate capacity.
_Avoid_: Paused Slice

**Abandoned Slice**:
A Slice deliberately ended without claiming its Success condition was met, because it became unnecessary, invalid, or superseded.
_Avoid_: Finished Slice, Paused Slice

**Capacity Constraint**:
A recurring rhythm, appointment, or obligation that consumes attention without independently creating a lasting portfolio outcome. It can support a Cake without becoming a Cake or Slice.
_Avoid_: Habit Cake, recurring Slice, routine Slice

**Task**:
An execution action inside a Slice. A Task does not independently occupy Pantry, Cake Stand, or Plate.
_Avoid_: Slice, Cake
