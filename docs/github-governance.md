# GitHub repository governance

Repository files can define CI but cannot by themselves prevent a direct push to `main`. The
repository owner must keep a branch ruleset for `main` aligned with these versioned expectations.

## Required `main` rules

- require changes to arrive through a pull request;
- require all review conversations to be resolved;
- require the branch to be current before merging;
- block force pushes and branch deletion;
- require these CI checks:
  - `Quality / Python 3.12`;
  - `Quality / Python 3.13`;
  - `Container / Python 3.12`.

While the repository has a single author/reviewer account, do not require an approving review:
GitHub does not allow an author to approve their own pull request. Add a one-review requirement
when an independent reviewer is available.

The ruleset is a GitHub setting rather than source code. After any CI job rename, update the
ruleset and this document together. Merging remains an explicit owner decision under ADR 0004.
