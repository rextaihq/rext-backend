# Migration Chain Notes

## Known Merge Points

This migration chain contains merge migrations (~13% of total). Key points to be aware of:

### Duplicate Merge Situation (2025-10-07)
- `1f31518bcc11` and `168db6d8bec3` both merge the same parents (`26ad95072497`, `seed006`)
- `3845ad0207e9` merges these two merge migrations
- This was a one-time coordination issue; treat `3845ad0207e9` as the canonical merge point

### Single-Parent Merge Cleanup
- `36ef85f33af2` (degenerate merge) was removed on 2026-02-10.
- Its child `b68e304117f0` was repointed directly to `g1h2i3j4k5l6`.

## Migration Workflow

To avoid creating additional merge migrations:
1. Always pull latest `main` and run `alembic heads` before creating a new migration
2. If multiple heads exist, create a single merge migration before adding new changes
3. Coordinate with the team before creating merge migrations
