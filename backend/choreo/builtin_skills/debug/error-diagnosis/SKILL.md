---
author: choreo
description: Use when diagnosing an error or exception — read traceback bottom-up before fixing
name: error-diagnosis
tags:
- debug
- error
version: 1.0.0
related_skills:
- python/uv-project
---

## Quick Decision

- `ModuleNotFoundError` → check install first (`uv pip list`) before reading code
- `KeyError` / `AttributeError` → print the offending object before assuming a bug
- `ConnectionRefusedError` / `TimeoutError` → verify the service is running first
- Error in a test assertion → expected; do NOT use this skill
- Otherwise → follow Steps below

## When to Use
- User pastes a traceback or error message
- An API call, test, or command is failing unexpectedly
- The cause of a failure is not immediately obvious
- Counter-trigger: do NOT use for known/expected errors (e.g. intentional test assertions)

## Steps

### 1. Read the full traceback — bottom-up
The actual error is at the bottom. The top is where it started. Read both ends before reading the middle.

### 2. Identify error category
| Category | Signal | First check |
|----------|--------|-------------|
| Import error | `ModuleNotFoundError`, `ImportError` | Is the package installed? Is the path correct? |
| Type error | `TypeError`, `AttributeError` | What type did we expect vs. what was passed? |
| Value error | `ValueError`, `KeyError`, `IndexError` | What value was expected? Print/log the actual value |
| Network/IO | `ConnectionError`, `TimeoutError` | Is the service running? Is the URL/port correct? |
| Permission | `PermissionError` | Check file permissions and path |

### 3. Reproduce minimally
Narrow to the smallest input that triggers the error. Remove noise.

### 4. Verify the fix
Run the exact failing command/test again after the fix — do not assume.

## Common Pitfalls
- Fixing the symptom not the cause (e.g. catching an exception instead of preventing it)
- Assuming the error is where the traceback starts — always read from the bottom
- Not checking whether the error is environment-specific (missing env var, wrong Python version)

## Verification Checklist
- [ ] Original failing command/test now passes
- [ ] No new warnings introduced
- [ ] The fix addresses the root cause, not just the symptom
