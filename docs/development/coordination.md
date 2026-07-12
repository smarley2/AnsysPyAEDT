# Multi-Agent Development Coordination

Codex, Claude, and human contributors must work through Git boundaries rather than sharing uncommitted changes.

## Task contract

Every implementation task must state:

- Owner
- Branch name
- Goal and non-goals
- Allowed files
- Upstream dependencies
- Produced interfaces
- Acceptance criteria
- Verification commands

## Branches and worktrees

- Codex: `codex/<task>`
- Claude: `claude/<task>`
- Human contributors: descriptive feature branches
- Use a dedicated worktree when two agents work in parallel.
- Never point two agents at the same working directory at the same time.

## Handoff format

A handoff must include:

1. What changed and why.
2. Files created or modified.
3. Public interfaces added or changed.
4. Commands run and their exact outcomes.
5. Known limitations or follow-up work.
6. Commit hash and pull-request link when available.

## Source of truth

- GitHub Issues track ownership and status.
- Approved specifications define product behavior.
- Implementation plans define task order and interfaces.
- ADRs explain architectural changes.
- Code and tests define implemented behavior.

Conversation history is not a source of truth. Any decision needed by another contributor must be written into the repository.
