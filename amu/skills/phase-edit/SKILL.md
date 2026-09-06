# Edit exactly one phase

## When to use
phase-edit

## Steps
- `amu plan --approve` then edit only that phase's files; finish with `amu check --phase N`

## Done when
- the command in the last step printed its `next` line and no blocking violation remains
