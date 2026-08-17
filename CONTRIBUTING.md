# Contributing

## Workflow

1. Start from the latest `main`.
2. Create an `agent/<short-description>` branch.
3. Make one coherent change at a time.
4. Run every required quality check.
5. Open a draft pull request with rationale, impact, validation, and limitations.
6. Merge only after explicit approval and green required checks.

## Commit style

Use concise conventional prefixes where helpful:

- `feat:` new behavior;
- `fix:` defect correction;
- `test:` test-only changes;
- `docs:` documentation;
- `chore:` tooling or repository maintenance.

## Definition of done

A change is complete only when:

- behavior and edge cases are tested;
- point-in-time semantics remain valid;
- type checking, linting, formatting, and tests pass;
- no secret or restricted dataset is introduced;
- documentation matches the implementation;
- limitations and unresolved evidence are explicit.
