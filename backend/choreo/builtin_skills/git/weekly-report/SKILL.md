---
author: choreo
description: Use when user wants to generate a weekly git commit summary report
name: weekly-report
tags:
- git
- report
version: 1.0.0
---

## When to Use
- User asks for weekly or periodic commit summaries
- Counter-trigger: do NOT use for individual commit messages

## Steps
1. Use `read_git_log` to get commits from the last 7 days
2. Group commits by type: feat / fix / chore / docs
3. Format as a Markdown bullet list
4. Optionally send via `send_notification`

## Common Pitfalls
- Check the date range — default is 7 days but user may specify differently
- Verify the repository path before reading

## Verification Checklist
- [ ] Commit count looks reasonable for the timeframe
- [ ] All commit types are represented
