# Cake

Cake is a personal portfolio system for deciding which enduring pursuits deserve attention and which bounded outcomes are being pursued now.

## Language

**Cake**:
A portfolio-level pursuit or direction that can yield one or more Slices. A Cake may be finite or long-lived, but it is always distinct from the actions used to advance it.
_Avoid_: Project, task, initiative

**Slice**:
One independently finishable outcome with observable success and exactly one parent Cake.
_Avoid_: Task, implementation step, entire Cake

**Pantry**:
The collection of possible Cakes that have not been admitted to the active portfolio. Pantry Cakes may still be vague, incomplete, or merely aspirational.
_Avoid_: Backlog, queue

**Cake Stand**:
The capacity-limited active portfolio of mature Cakes. A Cake belongs here only when it is an explicit commitment with a clear Direction and either current work or a valid Next Slice.
_Avoid_: Projects board, project list

**Plate**:
The capacity-limited set of Slices currently being pursued. Plate is the sole authority for whether a Slice is current work.
_Avoid_: Backlog, next queue, task list

**Next Slice**:
The single validated Slice nominated as a Cake's next pull-ready candidate. It is not a current Slice and leaves this role when pulled onto Plate.
_Avoid_: Current Slice, slice queue

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
