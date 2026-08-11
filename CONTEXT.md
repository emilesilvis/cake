# Cake

Cake is a personal portfolio system for deciding which enduring pursuits deserve attention and which bounded outcomes are being pursued now.

## Language

**Cake**:
A portfolio-level pursuit or direction that can yield one or more Slices. Its card links to every current Slice as derived navigation, while Plate remains authoritative for currentness.
_Avoid_: Project, task, initiative

**Slice**:
One independently finishable outcome with observable success, exactly one parent Cake, and exactly one canonical record on Plate. Its card links back to its parent Cake with a clickable Trello reference.
_Avoid_: Task, implementation step, entire Cake

**Pantry**:
The collection of possible Cakes that have not been admitted to the active portfolio. Pantry Cakes may still be vague, incomplete, or merely aspirational.
_Avoid_: Backlog, queue

**Cake Stand**:
The capacity-limited active portfolio of mature Cakes. It contains only Cakes, each admitted as an explicit commitment with a clear Direction and either current work or a valid Next Slice.
_Avoid_: Projects board, project list, Slice list

**Plate**:
The sole registry for Slices and the authority for whether a Slice is current work. Every Slice has one canonical Plate record; only current Slices consume Plate capacity.
_Avoid_: Backlog, next queue, task list

**Next Slice**:
The single validated Plate Slice linked by a waiting Cake as its next pull-ready candidate. It is mutually exclusive with Current Slices and leaves this role when pulled into current Plate work.
_Avoid_: Current Slice, slice queue

**Cake–Slice Link**:
A reciprocal clickable Trello reference in stable `https://trello.com/c/<shortLink>` form between a Cake and each current Slice. The Slice-to-Cake link identifies its parent; Cake-to-Slice links are derived navigation and never decide currentness. Membership transitions maintain both sides.
_Avoid_: UUID, copied status, alternate source of truth

**Delivery Link**:
An optional reciprocal reference between a Slice and an external work item such as a GitHub issue. Both records link to each other, while the Plate Slice alone owns identity and currentness.
_Avoid_: Canonical issue, GitHub-backed Slice, Slice source

**Being Eaten**:
The derived condition of a Cake that has at least one Slice on Plate. It is never stored as an independent status.
_Avoid_: Active label, in-progress Cake state

**Waiting on the Stand**:
A Cake Stand Cake with no Slice on Plate and exactly one valid Next Slice.
_Avoid_: Paused, inactive

**Parked**:
A mature Cake deliberately removed from the active portfolio without claiming that its Direction was achieved.
_Avoid_: Pantry, Failed, Paused Slice

**Finished**:
A Cake whose intended change or Direction has genuinely ended. Finishing a Cake does not imply that every resulting routine or interest ceases.
_Avoid_: Parked, archived

**Paused Slice**:
A Slice removed from Plate while remaining available for future nomination.
_Avoid_: Parked Cake, Blocked Slice

**Blocked Slice**:
A current Slice that cannot presently advance but still belongs on Plate and consumes Plate capacity.
_Avoid_: Paused Slice

**Abandoned Slice**:
A Slice deliberately ended without claiming its Success condition was met, because it became unnecessary, invalid, or superseded.
_Avoid_: Finished Slice, Paused Slice

**Capacity Constraint**:
A commitment such as an established routine, appointment, or obligation that reduces available attention without becoming a candidate Cake or Slice.
_Avoid_: Plate Slice, Cake Stand Cake

**Task**:
An execution action inside a Slice. A Task does not independently occupy Pantry, Cake Stand, or Plate.
_Avoid_: Slice, Cake
