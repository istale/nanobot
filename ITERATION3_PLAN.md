# Iteration 3 Plan (Document Only)

Branch: `feature/string-aware-parser`
Status: planning only (no code implementation in this iteration)

## Goal
Stabilize and operationalize current write_file parser behavior after Iteration 1/2 validation.

## Scope
- No parser-core redesign
- No edit_file migration yet
- Focus on observability, safety guards, regression coverage, and rollout readiness

## Work Items

### 1) Debug Trace (toggleable)
Add a debug mode for write_file parsing path.

Proposed toggle:
- `NANOBOT_WRITEFILE_DEBUG=1`

When enabled, log:
- whether fallback parser was used
- boundary mode used (`string-aware` vs `reverse-rfind` fallback)
- raw content length vs final content length
- quote/escape anomaly counters (if available)

Acceptance:
- Debug logs appear only when toggle is on
- No sensitive payload dump by default (log metadata only)

---

### 2) Distortion Detection Guards
Add lightweight warnings for likely corruption patterns.

Examples:
- suspicious terminal truncation pattern
- unresolved Python guard (`if name == "main":`)
- unmatched quote risk indicators

Behavior:
- warning only (non-blocking) in first rollout
- optional hard-fail mode can be discussed later

Acceptance:
- warnings are clear and actionable
- normal successful writes are not blocked

---

### 3) Regression Suite Expansion
Extend parser tests with synthetic fixtures for field-like scenarios.

Add cases:
- UNC + raw string mixed with regular Windows paths
- multiple `"}}` fragments inside string literals
- long content (500-1000 lines synthetic)
- mixed quotes / escaped quotes / triple quotes
- full-width quote contamination (`“ ” ‘ ’`) with expected behavior documented

Acceptance:
- tests deterministic and isolated
- all existing tests remain green

---

### 4) Iteration-4 Prep for edit_file (design only)
Document how write_file parser primitives could be reused for edit_file safely.

Document topics:
- reusable helpers
- differences in boundary semantics (`content` vs `old_text/new_text`)
- failure mode expectations

Acceptance:
- one short design note with explicit non-goals

---

### 5) Performance/Safety Checks
Define and test basic safety constraints.

Items:
- linear scan behavior under large payloads
- max payload guardrails
- fallback timeout/abort strategy (if needed)

Acceptance:
- no pathological slowdown in synthetic stress case
- failure path remains deterministic and recoverable

---

## Go / No-Go Gate for Iteration 3 Exit
Go if all are true:
1. Regression suite expanded and green
2. Debug trace toggle works as designed
3. Distortion warnings produce expected signals on synthetic bad cases
4. No regressions against current verified Iteration 2 behavior

No-Go if any is true:
- existing validated behavior regresses
- logs leak raw sensitive payload unexpectedly
- parser path introduces non-deterministic output on fixed fixtures

---

## Out of Scope (Explicit)
- Migrating parser logic to edit_file in this iteration
- Replacing parser with full AST/parser framework
- Introducing content_b64 workflow in this iteration
