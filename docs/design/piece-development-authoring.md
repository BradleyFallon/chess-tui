# Piece Development Authoring

Status: current interaction summary for Opening Rule Engine v4. See
[opening-rule-engine-v4.md](opening-rule-engine-v4.md) for authoritative
semantics and [rule-authoring-ui.md](rule-authoring-ui.md) for the full editor.

Each controlled original piece has at most one default development instruction.
Its alias and canonical `piece:<color>:<type>[:<qualifier>]` identity survive
movement. Clicking a moved or captured piece therefore inspects the same piece
script rather than whichever piece currently occupies its starting square.

A development instruction contains one destination, optional prerequisites, an
optional live condition, and a required explanation. Development order is a
separate semantic list. There are no structures, multiple competing
assignments, unlock/expiration lifecycle fields, or numeric priorities.

The instruction completes when its original piece first moves anywhere. An
interrupt or accepted exact-position move can therefore satisfy development.
A captured-undeveloped piece is terminal but does not satisfy a `.develop`
prerequisite. Python computes and returns the mechanical state and authoring
status.

The editor supports create, edit, preview, explicit Apply, dependency-safe
delete, and accessible Earlier/Later ordering. Invalid drafts never modify the
file or active workspace. Opponent pieces are inspectable relationship and
condition references but cannot receive authored movement.
