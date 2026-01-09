# AI Coding Instructions

---

## Part 1: Communication & Collaboration

### 1.0 Working Relationship

**Core Principle:**
User and AI are collaborative partners. User provides context, intent, and workflow knowledge. AI executes technically and contributes ideas. The goal is mutual understanding — most failures happen because we didn't align on intent.

**Before Starting Any Task (Non-Trivial):**

1. **Read and research first** — Review `PROJECT.md`, related files, existing patterns. Don't skip this, especially for new or multistep tasks.
2. **Echo back understanding** — Restate the task in plain English: what I understand you want, and why.
3. **Share my thinking** — Surface concerns, edge cases, gotchas, or alternative approaches I see. Discuss in plain English before touching code.
4. **Ask clarifying questions** — If anything is unclear or risky, ask *before* starting.
5. **Wait for go-ahead** — For non-trivial tasks, get confirmation before executing. Simple/obvious tasks (typo fix, rename) can proceed directly.

*No lazy questions* — Only ask what I couldn't answer by reading the code first.

**During Execution:**

- Understand the *why*, not just the literal instruction. Look at the bigger picture.
- Be a collaborator — share thoughts, suggest alternatives, push back if something seems off.
- Work efficiently — don't waste time on unnecessary steps.
- **No silent fallbacks** — If implementation deviates from what we planned, ask. Don't silently revert to old behavior.

**When Completing a Task:**

- Summarize: what I understood, what I did, and the results.
- Confirm: I've done due diligence and this is the most reliable solution I can provide.
- User will test in production and give immediate feedback if something's wrong.

---

### 1.1 Execution Autonomy

**Core Principle:**
If nothing bad will happen, do it. Only hesitate when there's actual risk or a better plan is needed.

**I handle automatically (no permission needed):**

- Reading files, searching code, exploring the codebase
- Running tests, debugging, fixing errors
- Creating helper/test scripts in `.helper_artifacts/`
- Iterating until the solution works
- Git commit and push after completing a large milestone (not every turn)
- Following steps you provide (while raising concerns if I see a better approach)
- Managing my own tasks and using all available resources

**I check with you first when:**

- There's a real risk (production data, paid APIs, deployments)
- I think there's a better approach than what you've outlined
- Implementation deviates from what we planned (no silent fallbacks)
- I'm genuinely unsure about business logic or intent

**Self-Management:**

- Follow every step necessary to ensure quality
- Use all resources available (files, tests, docs)
- Don't hesitate — ensure everything is done well

---

### 1.2 Research Before Asking

**Core Principle:**
Don't ask questions I could answer myself. Research first, then ask only if genuinely blocked.

**CRITICAL — Exhaust All Context Before Asking:**
Before asking the user ANY clarifying question, I MUST first exhaust all available means to gather context:

- Search the codebase (semantic search, grep, file exploration)
- Read PROJECT.md and related documentation
- Check existing implementations and patterns
- Review bug history and previous solutions
- Examine related files and modules

Only after I have done thorough research and still cannot find the answer should I ask the user. If I ask a question that could have been answered by reading the code or docs, that is a failure on my part.

**Research Order:**

1. **PROJECT.md first** — Understand the project context, expected behavior, known quirks
2. **Relevant code** — Read files directly related to the task (selective, not every line)
3. **Related patterns** — Search for similar implementations in the codebase
4. **Reference Library** — Check `.references/` for documented patterns
5. **Bug history** — Check if this problem was solved before

**Depth Guidelines:**

- Grasp basic concepts — understand what the project does and how things connect
- Be selective — focus on what's relevant to the current task
- Don't read every line of every module — understand enough to work effectively

**Within a Conversation:**

- If I have context from our earlier discussion, use it — don't re-research every turn
- Only go back to research when things get confusing or I realize I missed something
- Memory from conversation counts as valid context

**What NOT to Ask:**

- Questions answerable by reading the code
- Questions already covered in PROJECT.md
- Questions about patterns that exist elsewhere in the codebase

---

### 1.3 Reference Library

**Location:** `.references/` at workspace root

**Subfolders:**

- `ai/` — AI integration patterns
- `technical/` — API references (QuickBooks, etc.)
- `business/` — Business rules
- `patterns/` — Reusable code patterns
- `planning/` — Migration plans, project planning

**Usage:**

- Check references before asking for missing context
- Copy/adapt proven patterns from references
- Reference documentation first when working on integrations

---

## Part 2: Code & File Management

### 2.0 Code Style & Consistency

**Core Principle:**
Production code should be simple, readable, and understandable. Minimize complexity. Avoid "artistic" or over-engineered solutions.

**Minimalist Approach:**

- Write code that's easy to read and understand
- Avoid excessive abstraction — don't create classes/functions unless needed
- Keep logic straightforward — no clever tricks that obscure intent
- When logic changes, implement the new logic cleanly — no silent fallbacks to old behavior

**What to Avoid:**

- Excessive emojis in code or logs (keep them minimal and purposeful)
- Over-documentation (brief docstrings only where they add value)
- Verbose comments that restate what the code already shows
- Multiple redundant files — consolidate where possible

**Uniformity:**

- Match existing patterns in the codebase
- When multiple styles exist, prefer the cleaner/simpler one
- If uncertain, ask rather than guess

**Cleanup Policy:**

- Don't automatically clean up existing code while working on tasks
- If I notice something that needs improvement, suggest it — don't change silently
- Cleanup happens when explicitly requested

---

### 2.1 File Organization

**Folder Types:**

`.helper_artifacts/`

- Purpose: One-time scripts for debugging, exploring, gathering context
- Cleanup: Done in batches when you decide
- Scope (STANDARD - Option B):
    - Create `.helper_artifacts/` ONLY at a *top-level project root*.
        - Examples of project roots in this workspace: `automation files/01. personal/`, `automation files/02. westons/`, `automation files/03. storsafe/`.
        - The repo root `.helper_artifacts/` is reserved for truly cross-project helpers.
    - Inside that project-level `.helper_artifacts/`, create subfolders per subproject/feature.
        - Example: `automation files/01. personal/.helper_artifacts/find_hub_refresh/`
    - Do NOT create `.helper_artifacts/` folders *inside* subprojects (avoid sprawl).
        - Example: `automation files/02. westons/railway_app/automation/.helper_artifacts/` is not allowed.

**Hard Rules (keep it tidy):**

- At any *project-level* `.helper_artifacts/` root, keep only:
    - `.gitkeep`
    - Subfolders (feature/subproject buckets)
    - No loose scripts/files directly under the root
- Never keep generated caches under `.helper_artifacts/` (e.g., delete `__pycache__/`).

**Workspace-Root `.helper_artifacts/` (cross-project only):**

- Use the workspace-root `.helper_artifacts/` only for cross-project / machine / VS Code maintenance helpers.
- Organize these under `.helper_artifacts/workspace_maintenance/<topic>/...` (e.g., `terminal/`, `shortcuts/`, `workspace_json/`, `markdown/`, `bundles/`).

**Project-Root `.helper_artifacts/` (project-specific):**

- Always create a bucket folder first, then put helper scripts inside it.
- Prefer bucket names that match the business/feature area, not the technology.
- Examples:
    - `automation files/02. westons/.helper_artifacts/invoice/`
    - `automation files/02. westons/.helper_artifacts/onedrive/`
    - `automation files/03. storsafe/.helper_artifacts/08. Bank Reconciliation/`

`tests/`

- Purpose: Reusable test scripts that validate production code
- Cleanup: Keep permanently
- Scope: Per sub-project or per client if tests span projects

**Promotion Rule (Helper → Test):**

- If a helper artifact becomes reusable (run more than once, relied on for correctness, or useful as a regression check), promote it to `tests/`.
- Rename it to a stable `test_[feature]_[behavior].py` style name and make it runnable without manual edits.
- After promotion, remove or replace the original helper artifact (do not keep duplicate copies).

`logs/`

- Purpose: Runtime output
- Git-ignored

`PROJECT.md`

- Purpose: Single documentation file per project
- Contains: Overview, expected behavior, configuration, TODOs, bug history

**Where to Put Things:**

- Production code → Sub-project root folder
- **Project entrypoints → Sub-project root folder (discoverable):**
    - Each automated process folder should have exactly one obvious launcher at the top level named `RUN_ME.py`.
    - The launcher should be a thin wrapper that delegates to the real workflow runner (no business logic).
    - All other scripts/modules in that folder should live under an `internal/` subfolder to avoid “which file do I run?” clutter.
- One-time debug/helper scripts → `.helper_artifacts/`
- Reusable tests → `tests/`
- Documentation → `PROJECT.md` only (no extra .md files)
- Logs → `logs/`
- Credentials/secrets → Client root, git-ignored

**Workspace Root Files (expected in this workspace):**

- `*.code-workspace` files live at the workspace root as convenient “open this project” entrypoints.
- Use `.env` (git-ignored) for local environment variables; keep a per-project `.env.template` committed for onboarding.
- Prefer `GOOGLE_APPLICATION_CREDENTIALS` for the service account JSON path (and Railway Variables in production).
- Prefer per-project `requirements.txt` files under `automation files/<project>/requirements.txt`.
- Never hard-code absolute machine paths to secrets or credentials; prefer environment variables and paths resolved relative to project roots.

**Naming Convention for Helper Artifacts:**

- `test_[feature]_logic.py` — testing specific logic
- `debug_[issue].py` — debugging a specific problem
- `explore_[topic].py` — exploring/understanding something

**Path Robustness Rule (helpers should survive being moved):**

- Avoid hard-coded absolute paths for outputs.
- Write outputs relative to the helper’s folder:
    - Python: `Path(__file__).resolve().parent / "output.json"`
    - PowerShell: `Join-Path $PSScriptRoot "output.txt"`

**Helper Artifacts Safety Defaults:**

- Prefer `DRY_RUN = True` (or equivalent) when a helper can write files or call APIs.
- Write outputs under `.helper_artifacts/<subproject>/` (avoid cluttering project roots).
- Never store secrets/credentials in helper artifacts (even though they are git-ignored).

---

## Part 3: Development & Testing

### 3.0 Test-First Development

**Core Principle:**
For non-trivial logic changes, validate before applying to production.

**Option A: Temporary validation (one-time)**

- Create helper script in `.helper_artifacts/`
- Test the logic, show results, apply to production
- Delete later during batch cleanup

**Option B: Reusable test (permanent)**

- Create test script in `tests/`
- Can be run again later to verify code still works
- Keep forever

**When to use which:**

- Quick logic validation before applying → `.helper_artifacts/`
- Important logic that should be re-tested over time → `tests/`

**Requires testing first:**

- New calculations, algorithms, data processing
- API calls, database queries
- Business rules, complex conditionals

**Does NOT require testing first:**

- Simple renames, formatting
- Logging additions
- Config/constant tweaks
- Comments/docstrings

**Simulated Functional Testing:**
For everything you've worked on, always perform a simulated functional test — not just a syntax check. Verify the logic actually works as intended, not just that it parses correctly.

---

### 3.1 Development Patterns

**When creating new scripts:**

- Add `DEBUG = False` flag at top for troubleshooting
- Use `logger_config.py` for structured logging
- Use `debug_print()` for temporary tracing, `logger` for operational events

**Debug pattern:**

```python
DEBUG = False

def debug_print(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")
```

**Logger pattern:**

```python
from logger_config import setup_logger
logger = setup_logger(__name__)
```

**Logs location:** `logs/` folder (git-ignored)

---

### 3.2 Agent Execution State (Blocking) 

**Core Principle:**
Treat script/command execution as a blocking operation unless the user explicitly says otherwise.

1) **Execution is not complete until termination is confirmed**

Assume a process is still running until one of the following is true:

- The terminal process fully exits and returns control with a confirmed exit code
- A clear terminal completion marker appears (e.g., `DONE`, `COMPLETED`, `EXITING`)

❌ Do **not** assume completion based on partial output
❌ Do **not** proceed while a process is still alive

2) **If a script is still running, STOP and WAIT**

If execution does not terminate promptly:

- Pause workflow
- Explicitly acknowledge that execution is still in progress
- Recommend termination or timeout handling

Do **not**:

- Modify code
- Analyze outputs
- Suggest fixes
- Generate follow-up scripts

3) **Never analyze partial or early output**

Treat warnings, previews, or early logs as non-authoritative until execution completes.

4) **Detect and flag hanging/blocking behavior**

If a script:

- Does not exit
- Appears idle
- Keeps running after producing its main output
- Shows no progress indicators

Assume the process may be blocking or waiting.

5) **No parallel reasoning during execution**

Execution → termination → analysis.
Do not overlap these phases.

6) **Assume files may be locked until process exit**

While a script is running, assume output files may be incomplete/invalid.
Do not read output files, rewrite inputs, or rerun helpers on the same files until termination is confirmed.

7) **If execution behavior is unclear, ask before acting**

If unsure whether a process finished, pause and ask for confirmation rather than guessing.

---

### 3.3 Helper Scripts: One-Shot, Timed, and Verifiable 

**Goal:** Never leave processes running silently. Helpers must be bounded, self-terminating, and produce artifacts.

1) **No unattended long-running processes**

- Prefer bounded runs over interactive/continuous behavior.
- Watchers/servers/"tail" loops are not allowed unless explicitly requested.

2) **Always include a timeout**

- Every helper must accept a `--timeout-seconds` (or `--max-seconds`) CLI argument with a sane default (30–120s).
- If shell-level timeouts are unreliable, implement timeouts in Python.

3) **One-shot by default**

- No `while True` without an explicit stop condition and max-seconds/max-iterations.
- No background threads that keep the process alive.
- No “press any key to exit” behavior.

4) **Start/end banners are mandatory**

- Print a clear start banner.
- Print a clear end banner immediately before exit.
- End banner must include: status, elapsed time, and artifact paths.

5) **Capture outputs as artifacts**

- Write a structured summary file (JSON preferred), plus optional text preview.
- Summary should include: inputs, key counts, warnings, and key decisions/heuristics used.

6) **Definition of Done for an inspection helper**

A helper is acceptable only if it:

- Terminates automatically
- Has timeouts
- Produces a structured summary artifact (JSON/text)
- Prints enough progress to diagnose failures
- Scans all sheets/inputs and expands search when heuristics fail

**Template footer (print once, right before exiting):**

```
=== RUN END ===
status: COMPLETED | FAILED | TIMEOUT
exit_code: <int>
elapsed_seconds: <float>
artifacts:
    summary_json: <path>
    preview_txt: <path or null>
    other: [<paths>]
key_counts: { ... }
warnings: [ ... ]
FINAL_MARKER: COMPLETED
```

---

### 3.4 Document/Report Inspection: Deep Dive (No Shallow Scans)

**Core Principle:** When asked to inspect a workbook/report, do not glance at a small preview and guess. Fully map structure and validate assumptions so clarifications are minimized.

1) **Always perform a structured inspection checklist**

When inspecting Excel/Sheets/CSV-like reports, do ALL of the following unless the user explicitly narrows scope:

**A. Workbook structure**

- List all sheets/tabs in order
- Identify hidden sheets (if possible) and note them
- Record used range per sheet (approx rows/cols)
- Detect merged cells / frozen panes if relevant to parsing

**B. Header & layout detection**

- Locate title rows, period rows, entity/property columns, and header rows
- Detect multi-row headers and merged headers
- Detect column groups (e.g., property columns with Actual/Budget/Variance subcolumns)

**C. Data region mapping**

- Identify start/end rows for each major section (income, expenses, totals, etc.)
- Detect subtotal/total rows and how they’re labeled
- Confirm whether blank rows are separators vs missing data

**D. Data typing and formatting**

- Detect numbers stored as text, currency symbols, commas, parentheses negatives
- Identify date formats and period markers
- Check for inconsistent sign conventions

**E. Cross-check sanity**

- Verify a few totals/subtotals arithmetically from underlying lines
- Confirm columns align to the right entities (no shifted columns)
- Flag anomalies (unexpected zeros, missing entities, duplicated labels)

2) **Never conclude “not found” from a small window**

If a script says “not found within X by Y” or similar:

- Treat that as insufficient search, not a real conclusion
- Expand search across more rows/cols and all sheets
- Incorporate merged-cell awareness
- Use multiple heuristics (pattern + structure)

3) **Output must include evidence**

When reporting findings, include:

- Sheet names and where key regions are (e.g., “header rows 1–6; data starts row 9”)
- Previews from multiple relevant regions (header + first data block + totals area)
- Assumptions labeled as assumptions, and confirmed by sampling when possible

4) **Clarifications last, not first**

Before asking the user questions:

- Attempt to resolve ambiguity by inspecting more of the document
- Only ask what remains genuinely ambiguous after deep inspection
- Provide 2–3 plausible interpretations and the evidence for each

---

## Part 4: Version Control & Deployment

### 4.0 Git & Version Control

**Shorthand:**

- When the user says "commit", it means "commit + push" unless the user explicitly says "commit only".

**When to Commit:**

- After completing a large task/milestone (code works, tests pass)
- Don't commit/push on every turn; batch changes into meaningful milestones

**When to Push:**

- Immediately after committing (see shorthand above)
- Commit + push is a single operation unless the user requests otherwise
- Don't hold back unless there's a valid reason (merge conflict, broken tests)

**If Git Fails:**

- Report the error clearly
- Propose a fix (resolve conflict, retry push)
- Don't silently stop

**Commit Message Style:**

- Clear and descriptive
- Format: `type: description`
- Examples: `feat: Add overtime calculation`, `fix: Resolve mutex lock on exit`
- Types: `feat`, `fix`, `refactor`, `docs`, `chore`

---

### 4.1 Railway Deployment

**Separate from Git:**

- `git push` ≠ deployment
- Railway has its own deploy command: `push_to_railway.bat`

**When to Deploy:**

- Only when explicitly requested ("deploy to Railway" or "push to Railway")
- Never auto-deploy

**Pre-deployment Check:**

- Confirm code is committed and pushed to git first
- Verify tests pass locally

---

## Part 5: UI Development

### 5.0 UI Development

**Core Principles:**

- Uniformity — consistent look across the entire UI, no patchwork
- Elegant minimalist — clean, uncluttered, functional over decorative
- Visual verification before production — see changes before they're finalized

**Default Color Palette:**

- Primary: Navy blue
- Supporting: White, black, grey

**When Working on Front-End:**

- Provide suggestive styles for elements before implementing
- Present options for layout/design choices
- Get approval before building

**Visual Verification Process:**

1. Create static HTML preview in `.helper_artifacts/`
2. I open it in browser and verify it looks correct
3. Tell you: "Preview ready. Check `preview_xyz.html`"
4. You confirm visually
5. Apply to production

**Preventing Overlap Issues:**

- Reference existing working UI — copy patterns that work
- Use existing CSS classes instead of writing new CSS
- Smaller changes, more verification
- Check full context, not just the line being edited

---

## Part 6: Project Documentation

### 6.0 PROJECT.md Structure

**Purpose:** Reference document for AI to understand the project context. Single source of truth per project.

**Sections:**

1. **Overview** — What the project does (plain English, 2-3 sentences)

2. **Key Files & Roles** — Main files and what each one does

3. **How It Works** — The flow, how things connect

4. **Expected Behavior** — What should happen when things work correctly

5. **Configuration** — Environment variables, paths, settings

6. **How to Run/Test** — Commands to execute and verify

7. **Known Quirks/Gotchas** — Non-obvious behaviors or workarounds

8. **Current TODOs** — Active tasks (replaces separate TODO files)

9. **Bug History** — Significant bugs and how they were fixed

10. **Last Updated** — Date/time

**Bug History Entry Format:**

- **Symptom:** What was observed
- **Root Cause:** Why it happened
- **Key Insight:** The "aha moment" that led to diagnosis
- **Fix:** What we changed
- **Files Affected:** Which files were modified
- **Prevention Note:** Pattern to avoid in the future

**When to Update:**

- After significant behavior changes
- After adding new features
- After fixing challenging bugs
- Not for minor 1-2 turn bug fixes unless they reveal something important

---


