---
author: choreo
description: Use when writing or reviewing a git commit message for this project
name: commit-message
tags:
- git
- commit
version: 1.0.0
related_skills:
- git/weekly-report
---

## When to Use
- User asks to commit changes or write a commit message
- After completing a feature/fix and ready to save progress
- Counter-trigger: do NOT use for PR descriptions or changelogs

## Commit Message Format

```
<type>(<scope>): <short summary in imperative mood>

<optional body: WHY not WHAT, wrap at 72 chars>
```

### Types
| Type | When |
|------|------|
| `feat` | New feature visible to users |
| `fix` | Bug fix |
| `refactor` | Code change without behavior change |
| `chore` | Build/config/tooling |
| `docs` | Documentation only |
| `test` | Tests only |

### Scope (optional)
Use the module or area: `auth`, `mcp`, `skills`, `sandbox`, `frontend`

## Examples
```
feat(mcp): add streamable-http transport support

fix(skills): filter empty assistant messages before API call

chore: bump mcp package from langchain-mcp-adapters to native mcp>=1.0
```

## Steps
1. Run `git diff --staged` to review what's changing
2. Identify the type and optional scope
3. Write summary in imperative mood ("add", "fix", "remove") — not past tense
4. Add body only if the WHY isn't obvious from the diff
5. Commit: `git commit -m "type(scope): summary"`

## Common Pitfalls
- Do not start with capital letter after the colon
- Do not end summary with a period
- Summary should be ≤ 72 chars
- Do not write "this commit..." or "I added..."

## Verification Checklist
- [ ] Type is one of the table above
- [ ] Summary is imperative mood
- [ ] Summary ≤ 72 characters
