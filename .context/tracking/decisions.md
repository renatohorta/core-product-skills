# Decision Log (ADRs) — Core Product Skills

> Every important decision is recorded here with context and rationale.

---

## ADR-0001 — Source of truth in `.context/`

**Date**: 2026-08-18 · **Status**: Accepted

**Context**: The project context was spread across `.hermes/` and `.claude/`,
polluting the repository and tying the documentation to a specific agent.

**Decision**: All context is read and written in `.context/`. `CLAUDE.md` and
`AGENT.md` at the root are only pointers. Creating `.hermes/`/`.claude/` for
context is forbidden.

**Consequences**: Documentation portable across agents; a single place to
consult. `docs/` still exists for human-facing documentation — in case of
divergence, `.context/` prevails.

---

## ADR-0002 — `cp-full-dev` merged into `cp-orchestrator`

**Date**: before 2026-08-18 · **Status**: Superseded by ADR-0010 (the `cp-*` family was removed)

**Context**: The NEXUS pipeline (7 phases, 39 agents) lived in a separate skill,
triggered by the orchestrator via subprocess — an extra hop and two surfaces to
keep in sync.

**Decision**: NEXUS runs natively in the orchestrator via `NexusExecutor`; the
`cp-full-dev` skill was eliminated. Access is through the `full-dev` mode.

**Consequences**: Less indirection and automatic mode detection
(full/sprint/micro). In exchange, the orchestrator's `run.py` grew larger and
concentrates more responsibility.

---

## ADR-0003 — Provider-agnostic LLM resolution

**Date**: before 2026-08-18 · **Status**: Superseded by ADR-0012 (no LLM client in the skills)

**Context**: Without an explicit `llm=`, CrewAI falls into the OpenAI default and
fails with `OPENAI_API_KEY is required` even with another provider configured.

**Decision**: `skills/deprecated/_shared/llm.py` resolves the LLM in this order: agent env
vars → project `.env` → per-provider key detection → default
`gemini/gemini-2.5-flash`. Every skill uses `build_crew_llm()`.

**Consequences**: The skills work with the host agent's LLM (Hermes or Claude)
without code changes. `_shared` must be propagated to the **root** of each
agent's skills, not to the category.

---

## ADR-0004 — Communication between skills via subprocess + files

**Date**: before 2026-08-18 · **Status**: Accepted

**Context**: The orchestrator needs to trigger 14 other skills.

**Decision**: Triggering via `subprocess.run` with an argument list (no
`shell=True`), passing context by file (`_ctx_<phase>.txt`) and receiving
artifacts in `outputs/pipeline_<timestamp>/`.

**Consequences**: Each skill remains self-contained and independently
installable, and a skill that hangs does not bring down the orchestrator (600s
timeout per phase). In exchange, the CLI contract becomes implicit coupling —
hence the `invoke` metadata (and DT-03, which proposes validating it
automatically).

---

## ADR-0005 — Installation by destructive copy

**Date**: before 2026-08-18 · **Status**: Accepted

**Context**: Installed copies diverged from the repository when edited at the
destination.

**Decision**: `install.sh` does `rm -rf "$dst"` before copying; `__pycache__/`
and `outputs/` are removed from the destination after the copy.

**Consequences**: The install is always a faithful mirror of the repository and
local edits are discarded by design. Risk: pointing `HERMES_SKILLS_DIR`/
`CLAUDE_SKILLS_DIR` at a directory with its own content erases that content.

---

## ADR-0006 — Mode auto-detection instead of an optional flag

**Date**: before 2026-08-18 · **Status**: Superseded by ADR-0010 (applied to the removed `cp-*` family)

**Context**: Alternative skill modes controlled by an optional flag with
`default=False` were never triggered — the LLM calls the skill via function
calling and decides the parameters itself, without "remembering" the flag.

**Decision**: The correct mode is **detected** from the input content, not
declared by a flag.

**Consequences**: Skills work without extra instruction to the LLM. Requires
explicit, tested detection heuristics — and a clear fallback, to avoid falling
into a generic template without a signal that detection failed.

---

## ADR-0007 — All cp-* skills moved to `skills/deprecated/` (deprecated mode)

**Date**: 2026-10-04 · **Status**: Superseded by ADR-0010

**Context**: The 15 `cp-*` skills were the active product of the repository, but
the whole `cp-*` pipeline is being retired. Keeping them at the top of `skills/`
made `install.sh` and the test suite treat them as the current, installable
skills — the default `./scripts/install.sh` propagated them and `skills/cp-*`
glob was the implicit "the skills" location.

**Decision**: Every `cp-*` directory (and the `_shared` helper, which is not a
skill but is imported by all of them via the relative path
`.../scripts/run.py → parent³`) was moved with `git mv` into
`skills/deprecated/`. The skills are in **deprecated mode**: `install.sh`
installs **nothing** by default and only propagates them when given the explicit
`--deprecated` flag.

**Consequences**:

- `skills/` now contains a single subdirectory, `deprecated/`. The relative
  resolution (`parent³ = skills/deprecated`) is preserved because `_shared` moved
  together, so no skill had to change its imports.
- The test suite and `scripts/chat.py` point at `skills/deprecated/`
  (`tests/conftest.py`, `scripts/chat.py`).
- `install.sh` gained the `--deprecated` flag and a no-op default guard; the
  smoke test was split to assert both the no-op default and the opt-in listing.
- The skills are kept for historical reference; they are no longer an active
  pipeline. See `.context/docs/01-inception/vision-and-scope.md`.

---

## ADR-0008 — New active family: RUP skills under `skills/rup/`

**Date**: 2026-10-04 · **Status**: Accepted — layout (`skills/rup/`) amended by ADR-0010

**Context**: With the `cp-*` family retired (ADR-0007), the repository needed an
active skill family. The specification `~/Downloads/especificacao_agentes_rup.md`
defines a complete RUP agent team, strictly grounded in Kruchten's *The Rational
Unified Process: An Introduction* (3rd ed.): 9 disciplines, 1 orchestrator
(`RUP-Orchestrator`, base role Project Manager) and 20 specialized agents.

**Decision**: Create the **RUP family** under `skills/rup/` as the active family,
one skill per discipline (9 skills total):

- `rup-orchestrator` (governance + dispatcher)
- 8 discipline skills: `rup-environment`, `rup-business-modeling`,
  `rup-requirements`, `rup-analysis-design`, `rup-implementation`, `rup-test`,
  `rup-ccm`, `rup-deployment`.

Each skill follows the repository convention: `SKILL.md` + `scripts/run.py`
(self-contained CrewAI crew, agents embedded inline) + `references/` (agent →
artifact mapping, or the lifecycle for the orchestrator). The orchestrator
dispatches a discipline by running its `scripts/run.py` via `subprocess`
(same communication pattern as the deprecated orchestrator, ADR-0004).

**Consequences**:

- `install.sh` now installs the **active `rup` family by default**; the
  deprecated `cp-*` family requires `--deprecated` (both can be combined).
- `_shared/llm.py` is duplicated into `skills/rup/_shared/` (it is not a skill
  and is imported by every skill via the relative path
  `.../scripts/run.py → parent³ = skills/rup/`), keeping the two families
  independently installable.
- The test suite gained `tests/test_rup_smoke.py` (help/dry-run/exit codes,
  orchestrator registry == discipline skills); `tests/conftest.py` exposes
  `RUP_SKILLS_DIR`, `rup_skill_names()`, `rup_skill_script()`.
- Shared CLI across the family: `run.py "<briefing>" [--phase P] [--input F]
  [--output F] [--dry-run]`, plus `--discipline`/`--auto`/`--list` on the
  orchestrator. Provider-agnostic; exit codes 0/1/2/3 as the rest of the repo.
- Provenance: generated from the RUP specification; the family README and each
  `references/agents.md` record the discipline → agent → artifact mapping.

---

## ADR-0009 — Software Sizing & Effort Estimation (Use Case Points) in the orchestrator

**Date**: 2026-10-04 · **Status**: Accepted

**Context**: The RUP specification was updated to add, under the
`RUP-Orchestrator`'s strict responsibility, the artifact **Software Sizing &
Effort Estimation**: Function Point Analysis (FPA / IFPUG and NESMA), **Use Case
Points** (UCP: UAW/UUCW/UUCP, TCF/EF), and parametric estimates (COCOMO II,
SLOC/KLOC). The artifact feeds the Measurement Plan/Database and the Iteration
Plan, and matures across phases: preliminary/indicative in Inception (§3.1) and
baselined in Elaboration (§3.2).

**Decision**: Implement the **Use Case Points** calculation as a deterministic,
pure-Python function in `rup-orchestrator/scripts/run.py` (`compute_ucp`),
exposed through the CLI so it runs with **no LLM and no crewai**:

- `--estimate [--sizing <file>] [--json]` — compute UCP from a JSON sizing model
  (actors, use cases, TCF/EF factors, productivity h).
- `--sizing-template` — print an empty sizing model to fill in.
- `--list` was moved before `require_crewai()` so these deterministic commands
  never need the library or a credential.

The LLM-produced artifacts (FPA, COCOMO II/SLOC) remain part of the governance
Task; UCP is computed exactly in code because it is a deterministic formula.

**Consequences**:

- The neutral convention: **empty TCF/EF maps mean exactly neutral** (TCF = EF =
  1.0), and missing individual factors default to their mid-point (T = 2, F = 3).
- New reference `rup-orchestrator/references/sizing-estimation.md` documents the
  formulas, the 13 TCF and 8 EF factors, and a worked example
  (UUCP=185 → UCP=185 → 3700 h @ 20 h/UCP).
- Tests added in `tests/test_rup_smoke.py`: hand-calculated UCP match, neutral
  empty-factor behavior, and CLI `--estimate`/`--sizing-template` without an LLM.
- SKILL/docs updated (orchestrator SKILL.md, `skills/rup/README.md`,
  `docs/SKILLS.md`, `docs/ARCHITECTURE.md`).

---

## ADR-0010 — `cp-*` family removed; RUP skills flattened into `skills/`

**Date**: 2026-11-03 · **Status**: Accepted

**Context**: After ADR-0007/0008 the repository kept two families: the retired
`cp-*` skills under `skills/deprecated/` and the active RUP skills under
`skills/rup/`, each with its own copy of `_shared/`. The deprecated family was
dead weight — tests, `chat.py`, CI and docs still revolved around it — and the
extra `rup/` level only existed to separate the two. A review of the RUP family
also found defects: `--auto` wrote every discipline to the same `--output` (only
the last survived) and passed only the original briefing (no traceability
between disciplines); the governance prompt told the agent to use `compute_ucp`
without giving it any way to call it; `--dry-run` required crewai; `install.sh`
listed skills with GNU-only `find -printf` (nothing on macOS); installed skills
could not find `_shared` in Hermes' `skills/<category>/` layout; CI only ran on
pushes to `master` (the branch is `main`).

**Decision**:

- Delete `skills/deprecated/` (all `cp-*` skills and their `_shared`). They stay
  in the git history up to commit `6490694`.
- Move `skills/rup/*` to `skills/` (`skills/rup-*`, `skills/_shared/`,
  `skills/README.md`). `install.sh` installs every `skills/*` dir that has a
  `SKILL.md`; the `--deprecated` flag is gone.
- Each `run.py` looks for `_shared/` next to the skill and one level up, so the
  same copy works in the repo, in Claude Code (flat) and in Hermes (category).
- `--auto` chains the disciplines: each receives the briefing plus the earlier
  artifacts (`--input`, capped at 12 000 chars each), writes its own file
  (`<stem>.NN-<key>.md`) and the run stops at the first failure.
- The governance agent gets the `use_case_points_calculator` CrewAI tool
  (wrapping `compute_ucp`, with input validation); the task orders it to call
  the tool instead of computing by hand.
- `--dry-run` works without crewai (lists the planned agents); unreadable
  `--input` and invalid sizing models exit 1; `--output` creates parent dirs.
- CI triggers on `main`; `chat.py` targets the `rup-*` skills.

**Consequences**:

- The suite dropped the `cp-*` tests (contract `invoke`, quality gate, internal
  units, kanban flow) and gained coverage for the items above: 108 tests, no
  credentials. `tests/test_rup_smoke.py` became `tests/test_smoke.py`;
  `conftest.SKILLS_DIR` is `skills/`.
- The `.context/kanban/` flow is manual — the `cp-agile` daemon no longer exists.
- Writing the RUP artifacts into a target project's `.context/` was left open
  here and decided in ADR-0011.

---

## ADR-0011 — RUP artifacts are always persisted into `.context/`

**Date**: 2026-11-03 · **Status**: Accepted — recording mechanics amended by ADR-0012 (`--record`; no crew, no `--output`)

**Context**: The `rup-*` skills only printed their result and, optionally,
wrote it to `--output`. The RUP artifacts (Vision, SRS, SAD, Test Plan, Work
Orders, sizing…) therefore never became part of the project's source of truth,
`.context/` (ADR-0001), unless someone copied them by hand (INIT-02). The owner
decided persistence must be **mandatory**, not an opt-in flag.

**Decision**:

- Every real run of every `rup-*` skill writes its artifact to
  `.context/docs/<NN-phase>/rup-<skill>.md` — the phase folders already used by
  `.context/docs/` — and appends a row to `.context/tracking/rup-log.md`.
  `--estimate` writes `rup-orchestrator-sizing.md`. `--output` became an extra copy.
- **Naming**: the `rup-` prefix separates generated artifacts from the curated
  docs (`requirements.md`, `architecture.md`, …), which are never overwritten.
- **Policy**: regenerate the file per run and phase, with a provenance
  frontmatter (skill, discipline, phase, milestone, timestamp) and a briefing
  excerpt; history lives in git, the log keeps every write.
- **Which `.context/`**: `--context-dir` > `RUP_CONTEXT_DIR` > nearest
  `.context/` walking up from cwd, stopping at the git root (never escapes the
  repository) > `<git root or cwd>/.context`, created on first write. The
  orchestrator resolves it once and passes `--context-dir` to each child,
  because children run with cwd = the skills root.
- **Fail before paying**: writability is checked before `kickoff()`; failure
  exits with the new code **4** and no LLM call is made.
- `--auto` chains through `.context/`: each discipline receives the body (after
  `## Artifacts`) of the earlier disciplines' `.context/` files.
- Single implementation in `skills/_shared/context.py` (stdlib only).

**Consequences**:

- Running a skill always changes the project's working tree (new/updated
  `rup-*.md` + log). Commit them like any other context change.
- `--dry-run`, `--help`, `--list` and `--sizing-template` write nothing.
- Tests: a fake `crewai` (`tests/fakes/crewai/`) lets the suite run every skill
  end to end without an LLM; `clean_env` points `RUP_CONTEXT_DIR` to a temp dir
  and a guard test fails if anything lands in this repository's `.context/`.
  Suite: 138 passed.

---

## ADR-0012 — The host agent is the LLM; CrewAI, `llm.py`, proxy and chat removed

**Date**: 2026-11-03 · **Status**: Accepted

**Context**: The RUP skills ran CrewAI crews that needed their own LLM. The
agent invoking a skill (Claude Code, Hermes) does not pass its model or
credentials to subprocesses, so the crews had two options: an API key resolved
by `_shared/llm.py` (paid separately; with only `ANTHROPIC_API_KEY` set it still
picked the Gemini default model and failed), or `scripts/claude_proxy.py`
(`claude -p` per call: dropped the assistant turns CrewAI's loop relies on,
ignored `tools` — so the UCP tool could not be called — slow and quota-hungry).
Either way it was a **second** LLM, without the conversation context the agent
already had.

**Decision**: The agent running the skill is the only LLM. The skills became
deterministic, standard-library programs with a two-step protocol:

1. **Work packet** — `run.py "<briefing>" --phase P` prints the roles (goal,
   perspective, mission), the exact required artifacts, RUP rules, the briefing,
   the earlier artifacts recorded in `.context/` (governance + earlier
   disciplines of the phase) and the exact `--record` command.
2. **Record** — `run.py --record FILE|- --phase P` checks that every required
   artifact has a `## <Artifact>` section (else lists them, writes nothing,
   exit 1) and writes `.context/` (ADR-0011).

- Each discipline's `run.py` is now its `SPEC` (roles/missions/artifacts as
  data, extracted verbatim from the former crews) + `_shared/discipline.py`.
- `_shared/rup.py` is the single registry (phases, ordered disciplines, exits).
- Orchestrator: governance packet (with the exact `--sizing-template` /
  `--estimate` commands — UCP is never computed by the model), `--discipline`
  (that skill's packet), `--auto` (iteration protocol, in order), `--status`.
- **Removed**: `crewai` dependency, `_shared/llm.py`, `scripts/claude_proxy.py`
  (and its tests), `scripts/chat.py`, `.env.example`, `--dry-run`, `--output`,
  exit codes 2 and 3.

**Consequences**:

- Same model and context as the conversation; no key, proxy or extra cost;
  real tool use by the host (it runs `--estimate` itself).
- No runtime dependency (tests run the skills with `python -S`); suite from ~50 s
  to ~3 s; the fake crewai is gone — E2E tests record fixed documents.
- The skills can no longer run unattended without an agent (CI, cron): the
  artifacts are written by whoever runs the protocol.
- `--auto` no longer executes anything: it prints the protocol; the agent runs
  the steps in order (each packet embeds the earlier steps' artifacts).
- Security surface shrank: no socket, no credential read (SEC-02 closed).

---

## ADR-0013 — Execution skills, authorization gate, cards and roadmap in `.context/`

**Date**: 2026-11-03 · **Status**: Accepted — amends ADR-0011 (silent creation of `.context/`); extends ADR-0012 (same protocol, host agent is the LLM)

**Context**: The owner ran the whole development cycle (discovery, planning,
TDD, debugging, review, git hygiene) with the *superpowers* plugin. Its
documentation is hard to follow and it writes outside `.context/`
(`docs/superpowers/...`). The owner wants the state of the work readable in
`.context/` (epics, stories, tasks, a roadmap, cards that move between columns)
and tests that prove something. Separately, ADR-0011 created `.context/` and
wrote into it silently, which is unsafe in projects that already have
documentation (`.specs`, `.doc`, `docs/`, a non-standard `.context/`).
Design: `INIT-03-rup-execution-skills-design.md` (approach B: keep the 9
document skills, add focused execution skills).

**Decision**:

- **Authorization gate (amends ADR-0011).** A `.context/` is authorized when it
  holds the marker `.context/.rup-standard` (version, who, when). Every writing
  command of every skill checks it in `_shared/context.py`; without it nothing
  is written and the skill exits with the new code **5**, printing what was
  found, what would change and "ask the user; on approval run
  `rup-context --init`". Read-only packets still work, with a warning. Any
  `.context/` without the marker counts as non-standard, including this
  repository's own: one authorized `--init` per project.
- **`rup-context`**: `--status` (read-only), `--init --authorized-by "<who>"`
  (adds missing folders and skeleton files, the marker, and a RUP pointer block
  in `CLAUDE.md`/`AGENT.md`; never overwrites or deletes), `--import` /
  `--record-import` (existing docs are appended in `<!-- rup-import -->` blocks
  or create missing files; originals untouched).
- **Six execution skills** replace the plugin: `rup-context`, `rup-discover`
  (conversation, records `rup-discover.md`, embedded first in later packets),
  `rup-backlog` (cards, moves, roadmap, views), `rup-build` (TDD start/finish),
  `rup-debug` (bug cards, root cause before fix), `rup-review` (checklist and
  verdict). They reuse the packet -> document -> record protocol or plain
  state-changing commands. The 9 document skills are unchanged except for the
  marker check (shared code), `rup-discover.md` in `prior_artifacts()` and one
  governance instruction (allocate epics to iterations with `rup-backlog`).
- **Cards**: `EP-NNN`, `ST-NNN`, `TK-NNN`, `BUG-NNN`, IDs assigned by the skill,
  one file per card in `.context/kanban/<column>/<ID>.md`, frontmatter + fixed
  sections validated on creation, `## History` always last. Acceptance criteria
  get stable IDs `ST-NNN/AC-n`; a task's `## Covers` references them; stories
  and epics roll up automatically. Derivation from `rup-requirements` only adds
  cards.
- **Roadmap**: `.context/roadmap/R<n>.md` (releases) and `R<n>-I<m>.md`
  (iterations, with a RUP phase); epics are planned into iterations. Generated
  views `docs/06-roadmap.md` and `docs/06-board.md` are rewritten after every
  change and never hand-edited; the curated `06-kanban.md` is left alone.
- **Declaration-based moves**: `--move ID COLUMN --reason` is enough, any move
  is legal, a skipped column only warns in History. No proof is required.
- **Test-value checks** (`rup-build --finish`): the tests listed in the delivery
  must exist, reference a criterion of the parent story (or the bug ID), cover
  every `Covers` criterion, assert something non-constant, call project code and
  carry red evidence. Python is analysed with `ast`, JS/TS by pattern, other
  languages by name only. A failure records nothing (exit 1).
- **No git, no test runs in the skills.** Packets tell the agent which branch
  and commits to make; the card records the branch.
- **Triggering** replaces the superpowers session hook: the pointer block added
  by `--init`, no hook installed (works in Claude Code and Hermes).

**Consequences**:

- Exit code 5 joins 0/1/4. Every project, including this repository, needs one
  authorized `rup-context --init` before skills write again.
- 15 skills (9 document + 6 execution) plus `_shared` (adds `consent.py`,
  `frontmatter.py`, `cards.py`, `roadmap.py`, `testcheck*.py`); still stdlib
  only and tested with `python -S`. Suite: 268 passed.
- Old card schema (`TASK-NNN`, `task|bug|tech-debt|initiative`) is superseded;
  existing cards are not migrated automatically.
- Test checks are a brake on declared tests, not proof that they ran or pass.
- Uninstalling the superpowers plugin remains the owner's call.

---

## ADR-0014 — RUP skills renamed from `rup-*` to `cp-*`

**Date**: 2026-11-03 · **Status**: Accepted

**Context**: The owner asked for every skill to use the `cp-` prefix (Core
Product) instead of `rup-`. The prefix was already used by the legacy Software
Factory family removed in ADR-0010; those skills only exist in the git history,
so the names are free again.

**Decision**: Rename all 15 skills (`skills/rup-<name>` → `skills/cp-<name>`,
`git mv`) and every reference to their names: `SKILL.md` frontmatter, the
registry in `_shared/rup.py`, generated artifact names
(`.context/docs/<NN-phase>/cp-<skill>.md`, `cp-orchestrator-sizing.md`),
derivation sources (`cp-requirements#<heading>`), the pointer note, docs and
tests. Internal identifiers that are not skill names keep their names: the
marker `.context/.rup-standard`, the log `tracking/rup-log.md`, the
`<!-- rup-import -->` / `<!-- rup-skills:… -->` markers, `RUP_CONTEXT_DIR`,
`RUP_SKILLS_PYTHON` and the module `_shared/rup.py` (they name the RUP method,
not a skill). Historical records (ADR-0001…0013, `inbox/processed/`,
`translation-map.md`) are not rewritten.

**Consequences**:

- Agents must invoke `cp-orchestrator`, `cp-context`, `cp-backlog`, etc.;
  reinstall with `./scripts/install.sh` (old `rup-*` installed copies, if any,
  must be removed by hand — `install.sh` never deletes other skills).
- Artifacts recorded before the rename (`rup-<skill>.md`) are not migrated.
- Older ADRs mention `cp-*` meaning the legacy Software Factory; from ADR-0014
  on, `cp-*` means the RUP skills.

---

## ADR-0015 — Root `docs/` removed; `.context/` is the only documentation

**Date**: 2026-11-03 · **Status**: Accepted

**Context**: The repository kept two documentation trees: `.context/` (source
of truth for agents, ADR-0001) and a root `docs/` (`ARCHITECTURE.md`,
`INSTALLATION.md`, `SKILLS.md`) as a human-facing presentation copy. Every
change had to be written twice, and the copies drifted.

**Decision**: Delete the root `docs/`. `.context/` is the only documentation
of the project; the human entry points are `README.md` (overview, install,
tests) and `skills/README.md` + each `SKILL.md` (catalog). The content of the
removed files already lived in `.context/docs/02-elaboration/architecture.md`,
`.context/docs/04-transition/devops-infra.md` and the skill READMEs.

**Consequences**: Links now point into `.context/docs/`. `cp-context --status`
no longer reports `docs` as another documentation directory in this repository.
The removed files remain in the git history.

---

## ADR-0016 — cp-test measures the value of the tests (mutation testing)

**Date**: 2026-11-04 · **Status**: Accepted

**Context**: In a real project (Django + DRF, 577 tests), the cp-test packet asked
for the RUP test artifacts but never for measured numbers, and had no way to
answer "are our tests worth anything?". Line coverage was 96%; a mutation run
done by hand outside the skills scored 76%, with whole modules under 50%, and
an independent review found 12 real defects with the suite green. The scripts
were improvised (`MELHORIAS-cp-testes.md`).

**Decision**:

- The cp-test packet demands measured evidence (command, SHA, duration, result
  for every execution) and a new Test Manager artifact, **Test Value
  Assessment**. It embeds `.context/tests/{baseline,static-audit}.md` and
  `tests/mutation/{report,triage}.md` when they exist.
- `cp-test --audit` prints the protocol A0–A8 (profile, baseline, inventory,
  static audit, module choice, mutation, triage, action, record).
- Deterministic tools in `_shared/mutation.py` and `_shared/testaudit.py`
  (stdlib): Python AST mutants; a parallel, resumable runner in disposable copies
  of the project; per-module report; triage table checked against fixed rules
  (equivalent / real gap / dead code / out of scope, each with a reason; real gap
  → card; dead code → CR).
- **Exception to "the skills never run the project's tests"**: `cp-test --mutate`
  runs the suite command the agent wrote in `.context/tests/profile.json`, only in
  copies (the original is never written). Git is still never run: the SHA is read
  from `.git`. The run fingerprints every non-test file and refuses to continue
  if the code under test changed (test files may change: that is how a gap is
  closed, re-running the survivors).
- cp-build asks for mutation of the changed lines (`## Mutation` in the
  delivery; its absence is a warning, not a rejection); cp-review shows it and
  recommends an adversarial review; cp-debug requires the fix's mutants to die;
  the orchestrator routes test-value demands to `--audit` and adds the mutation
  score to the Measurement Plan.

**Consequences**: Mutation can take hours: `--budget` and resume, `--mutation-status`.
Non-Python projects use their ecosystem tool (Stryker, PIT, go-mutesting,
cargo-mutants) with the same protocol and JSONL format. The `## Mutation`
warning in cp-build can become a gate later. Items P1, P2, P3 and P5 of the
source document (record overwrites a phase, commit hint, `--init` summary,
estimate × actual) are not part of this decision.

## ADR-0017 — cp-orchestrator is the front door: the agent routes, the user never names a skill

**Date**: 2026-11-04 · **Status**: Accepted

**Context**: The team guide showed that a user had to know and call each skill
by name (`cp-discover` for discovery, `cp-requirements` for requirements, …).
The orchestrator only knew governance and the 8 disciplines; it did not know
the execution skills (discover, backlog, build, debug, review, test audit) and
did not route a plain request.

**Decision**:
- `cp-orchestrator --route "<request>"` prints a read-only routing packet: the
  request, the project state read from `.context/` (authorization, discovery,
  requirements, governance, board per column, open bugs), a suggested next step,
  every route with its exact command, the standard chains and the gates.
- Classification stays with the agent (ADR-0012): no keyword matching in code.
  The code only reads state and suggests, in this order: authorize → review →
  finish what is in 3-doing → open bugs → discover → requirements → derive the
  backlog → build what is in 2-todo → plan the backlog → ask the user.
- The agent runs the chain itself and stops only at the gates: authorizing
  `.context/`, the discovery conversation, confirming derived cards, a real
  ambiguity (one question), destructive or outward-facing actions. It never
  answers "call cp-xxx".
- The orchestrator SKILL.md description says it is the front door for any
  project request; the pointer note in CLAUDE.md / AGENT.md starts with the
  `--route` line, and `cp-context --init` refreshes an outdated pointer block
  between its markers (text outside the markers is never touched).

**Consequences**: The other skills keep working when called directly. Projects
initialized before this decision get the new pointer note by running
`cp-context --init` again (it only adds what is missing, plus the refresh).

---

## ADR-0018 — the audit owes a verdict for every module it discovered (audit closure)

**Date**: 2026-11-16 · **Status**: Accepted

**Context**: ADR-0016 gave cp-test a mutation score per module, and A6 triage
forces a verdict for every survivor. What stayed silent is the surface the audit
never touched: a report saying "mutation score 87%" over three modules reads as
"the tests are fine" while forty modules were never mutated. That is the same
failure mode ADR-0016 fixed for line coverage, one level up — and the most
dangerous default a Test Value Assessment can have, because a clean-looking
report implies the rest was checked. The pattern was proven in a sibling codebase
(Claude-BugHunter, `engine/closure.py`): a hard closure gate where a discovered
`(host, class)` pair owes a verdict, `blocked` is not covered, and the caveats in
the report are generated from the ledger instead of being written by hand.

**Decision**:

- `cp-test --audit-closure` (step A7, between triage and action) builds the
  ledger of the audit's own coverage: every source module in the declared surface
  — `profile.source_extensions` (default `[".py"]`), minus test files, minus
  `copy_ignore` trees, minus the new `profile.audit_exclude` globs — gets exactly
  one verdict: `audited` (a mutant was graded), `waived` (explicit, with reason),
  `blocked` (mutants ran, none was graded: all `error<N>`/`invalid`) or
  `never_audited`.
- The gate is hard: while any module is `blocked` or `never_audited` the command
  exits `1` and writes `.context/tests/closure.md` with a "Not audited — do not
  read as passing" section generated from the ledger.
- The escape hatch is explicit and reasoned: `cp-test --waive <path|glob>
  --reason "…"` records the decision in `.context/tests/closure-waivers.json`.
  A reason under 12 characters is rejected. A waiver is a decision that ships in
  the report, not a silent omission.
- `closure.md` joins the evidence files the packet embeds, and the packet's
  instructions require the Test Value Assessment to state the audit's own
  coverage: a score over a subset is never a statement about the code it did not
  touch.
- Pure standard library (`_shared/auditclosure.py`, functions over
  `results.jsonl` + the waivers file), testable without running a mutant.
- Fixed along the way: `--profile-template` crashed (`TypeError` on `Path(None)`)
  because the early return came after the project-root resolution, even though
  A0 of the protocol points at it.

**Consequences**: An audit that covers a subset now says so, and the Test Value
Assessment cannot look cleaner than the work behind it. Projects with large
surfaces will see `--audit-closure` fail until they either mutate the modules or
waive them with a reason — that is the point, and the waiver file makes the
trade-off auditable. The surface is declared in the profile, so non-Python
projects declare their extensions instead of the module guessing.


---

## ADR-0019 — the skills learn from superpowers: trigger-first descriptions, a task brief, the verification gate and two verdicts

**Date**: 2026-11-16 · **Status**: Accepted

**Context**: `obra/superpowers` (v7.0.2) was evaluated against the `cp-*` family
to see what is worth importing. It is the opposite architecture — prompt-only, no
state, no deterministic tooling — so most of it does not fit: we already have the
persistence (`.context/`), the gates and the measurement (mutation, closure) it
lacks. But three of its disciplines are stronger than ours, and they were measured
there rather than asserted:

- the **`description` is the only text a harness always shows**, so it must state
  when to use the skill and never summarize its workflow (an agent that reads the
  summary follows the summary instead of opening the skill);
- a **task brief** with exact interfaces, verbatim constraints and a review focus
  is what lets a task be executed (or dispatched) without the whole conversation;
- **evidence before claims** (verification-before-completion) and **two separate
  verdicts** (spec compliance vs code quality) with a review package handed to the
  reviewer as a file, not as a session.

**Decision**:

- Every `SKILL.md` description opens with the trigger (`Use when …`), stays under
  400 characters and says nothing about the workflow; `cp-orchestrator`'s drops
  from 775 to 327 characters. `tests/test_skill_contract.py` enforces the trigger,
  the length and the 20 KB compaction budget (Claude Code truncates a re-attached
  skill past 20,000 characters).
- `cp-discover` gains the conversation ritual it was missing
  (`references/brainstorming.md`): look before asking, echo the request, lay out
  the approaches **before** writing, play back in 200-300 word chunks, size the
  work, and do not build before approval.
- A card may carry `## Interfaces`, `## Constraints` and `## Review focus`
  (`cp-backlog` `references/cards.md`). They are the task brief: optional, never
  invented by the skill, printed by `cp-build --start` and checked by `cp-review`.
- A delivery now needs `## Verification` — `Command:`, `Result:` and `Commit:` of
  the green run — on top of the red evidence (ADR-0016). `cp-build --finish`
  rejects it without those three lines, and `## Rulings` records every deviation
  as `what — why — what it costs`. `Commit:` accepts `none — <why>` when the
  project is not a git repository: the first behavioural run showed the gate
  demanding a SHA that cannot exist (skill-testing.md).
- `cp-review` records **two** verdicts: `## Spec` (`pass`/`gap`) and `## Quality`
  (`approved`/`changes`). `approved` requires both; a thing the reviewer could not
  check is a `- Cannot verify:` finding, never a pass. `--package ID` writes
  `.context/reviews/<ID>.md` — the file the reviewer reads — and the merge step
  now requires the full suite green **on the merged result**.
- `cp-debug` gets the four phases and boundary instrumentation
  (`references/debugging.md`), and `## Root cause` must carry an `Evidence:` line;
  `--diagnose` rejects the document without it.
- `cp-build --status [ID]` answers "where was I" from the cards (delivery,
  verification, mutation, last history line) — the resume map that survives a
  compaction.
- `cp-build/references/dispatch.md` documents handing a card to a subagent (Claude
  Code's Task, Hermes' `delegate_task`): five-part dispatch, no nested reviewers,
  verify the report instead of trusting it.
- Skill changes are tested as behaviour, not only as contracts:
  `docs/04-transition/skill-testing.md` (RED baseline without the change, minimal
  rule, close the loopholes, match the form to the failure).

**Consequences**: Two of the three new gates (verification, spec+quality) will
reject work that used to pass — that is the point, and the messages say what is
missing. Existing deliveries and reviews in `.context/` keep their old shape:
gates apply to what is written after this decision. Not imported: the
SessionStart hook (our install + pointer note covers it, and a bash hook per
harness is a maintenance cost we are not paying), the "your human partner" voice,
and the 15 process skills that would duplicate `cp-discover`, `cp-backlog`,
`cp-build` and `cp-review`.


---

## ADR-0020 — cp-operation-pentest: the operation family begins with a white-box code security audit

**Date**: 2026-11-19 · **Status**: Accepted

**Context**: The cp-* skills stop at delivery (Inception→Transition). The product needs
a factory that continues into operation/sustainment (monitoring, maintenance, infra,
security). Separately, the sibling `Claude-BugHunter` repo (Sachin Sharma, MIT + CC-BY-4.0)
holds strong vulnerability-detection knowledge (58 `hunt-*` skills, the 7-Question Gate,
evidence hygiene, a coverage-closure engine). Only its closure gate had been mined so far
(ADR-0018). The team's security need is defensive and white-box: find holes in our *own*
polyglot code, not attack third parties.

**Decision**: Start a `cp-operation-*` family; its first member is `cp-operation-pentest`,
v1 = source-code security audit, mirroring `cp-test --audit`:

- `run.py` prints a work packet (vulnerability classes + `references/` + the discovered
  source surface + the assessment format); the agent (the LLM) audits the source and writes
  one assessment document; `--record` validates it, opens one `BUG-NNN` per confirmed finding
  (deduped; a "cannot verify"/killed verdict opens none), and closes the coverage ledger.
- Coverage is tracked per `(module × vulnerability-class)` pair, cumulative across `--record`
  runs; the gate exits 1 while any pair is never audited and not waived
  (`.context/operation/pentest/closure.md`). `--waive PATH|GLOB --reason "…"` is the reasoned
  escape hatch. Modelled on BugHunter's `engine/closure.py` (host × class), like ADR-0018.
- "Audited" comes from the agent's declared `## Coverage` (there are no mutants), cross-checked
  against the walked surface. Same trust model as the rest of cp-*.
- The surface is polyglot: `cp-operation-pentest/profile.json` declares `source_extensions`
  (`.py .js .ts .tsx .java .kt` …) so the gate sees the whole codebase, not just `.py`.
- The 11 class `references/*.md`, `triage.md` (7-Question Gate) and `evidence.md` are condensed
  from and credited to Claude-BugHunter in `NOTICE` (no verbatim redistribution).
- `cp-orchestrator` routes to it via a `pentest` route + a security chain in `_shared/router.py`;
  the family is registered for routing so future members (`cp-operation-monitor`, …) slot in.
- Confirmed findings become BUG cards (kanban, phase-independent), so the **5th "Operation"
  lifecycle phase is deferred** until an operation skill needs a phase-doc artifact.
- No label field added to `cards.py` in v1: security metadata goes in the BUG body + a
  `[security]` title prefix.

Not in v1 (deferred): the `--infra URL` mode (running-service/DAST audit, reusing BugHunter's
`scope.py`); the rest of the BugHunter engine (`agent.py`/`engine.py`) stays out — it dispatches
models (ADR-0012 forbids it).

**Consequences**: Security review becomes a routed, defensive, white-box step that feeds the
existing pipeline instead of a side report. A clean finding list can no longer hide unaudited
code. The operation family has a pattern the next members follow. Pure stdlib, `python -S`.


---

## ADR-0021 — cp-operation-pentest --infra: a map-only, deterministic surface map

**Date**: 2026-11-19 · **Status**: Accepted (extends ADR-0020)

**Context**: ADR-0020 shipped the code-audit mode and deferred the running-infra mode. The
team wants to audit its own running services too, defensively. BugHunter's engine maps a
target deterministically (recon → arsenal map, $0, no agents) and only probes under an
opt-in `--hunt`. Our repo is stdlib and offline-testable, so a crawler (gau/katana/httpx)
does not belong in a skill.

**Decision**: `cp-operation-pentest --infra SCOPE.json` is **map-only and deterministic**:

- Scope is a JSON file (`name`, `in_scope`, `out_of_scope`, `seeds`, `endpoints`, optional
  `openapi`), enforced by `_shared/scope.py` — an allowlist with **deny-wins** and
  **default-deny** (exact host, `*.wildcard`, CIDR). Adapted from BugHunter's `engine/scope.py`.
- The surface is **declared, not crawled**: endpoints come from the scope file's `endpoints`
  or a parsed OpenAPI file. No network, no probing, nothing touched — safe by construction,
  and testable offline.
- Each in-scope endpoint is mapped to the vulnerability classes worth auditing via a
  path/param-name heuristic (`pentest.infer_classes`, always non-empty); out-of-scope
  endpoints are listed and not mapped. The map is a hint for the auditor, never a limit.
- Findings are recorded exactly as in the code mode (`--record` → one BUG per confirmed
  finding). Active probing (an opt-in `--hunt`, curl-first, read-only) and endpoint-level
  coverage are a deferred future mode; the rest of BugHunter's engine (agent dispatch) stays
  out (ADR-0012).

**Consequences**: The team can point the skill at a scope file and get a scoped, safe map of
which checks apply where, feeding the same pipeline. `_shared/scope.py` is now available to any
cp-operation-* member. No crawler dependency; still pure stdlib, `python -S`.


---

## ADR-0022 — cp-ui: design system before code, UI audit after code

**Date**: 2026-11-19 · **Status**: Accepted (second exception to "skills never run the project's commands"; the first is ADR-0016)

**Context**: Products built through the cp-* pipeline come out **generic** (no visual identity
is ever decided; the agent falls back to the same defaults per screen) and **full of UI bugs**
(nothing in the pipeline looks at the interface: low contrast, no focus ring, horizontal
scroll at 360 px, missing states reach `7-done`). UI exists only as a role inside
`cp-analysis-design`. The sibling repo `ui-ux-pro-max-skill` (UUPM, MIT, NextLevelBuilder)
has curated styles, palettes, font pairings, UX rules and a Playwright audit worth mining.
Design: `inbox/processed/cp-ui-design.md`.

**Decision**: Approach A — one new skill, `cp-ui`, with two moments, plus small hooks.

- **Four operator decisions.** (1) Each product's identity is chosen by the skill operator,
  never by the skill: `--design-system` proposes 2-3 distinct accessible directions with an
  HTML preview each, a person picks/mixes/edits, and `--record` requires `--chosen-by` and a
  filled `## Decision`; replacing needs `--force --reason`. (2) Playwright is optional: the
  audit works without it and says so. (3) Findings do not block: each confirmed finding is a
  `BUG-NNN` (grouped one per rule x file, deduped against open BUGs; a finding after the BUG
  reached `7-done` opens a new one) and the delivering card moves on. (4) For BUGs opened by
  cp-ui the fix evidence is a re-check, `cp-ui --audit --verify BUG-NNN`, accepted by
  `cp-build --finish` instead of a regression test (cards carry `source: cp-ui`).
- **Audit in three layers with an honest header** (static / visual / checklist): static regex
  candidates the agent must confirm or dismiss; the product's optional visual audit; an
  evidence checklist where `not-verified` stays visible. `0 files` or an unanswered item is
  never reported as "clean".
- **UUPM v2.15.0 (2de1134) vendored verbatim** in `skills/cp-ui/vendor/uupm/` with its
  `LICENSE` and a `NOTICE` entry, loaded in-process, offline, `python -S`; our direction
  composer, `_shared/uikit.py` (MASTER.md parse/validate/tokens) and `_shared/uicheck.py`
  (static checks, visual, verify) sit around it. `tokens.json` is derived from MASTER.md.
  `templates/ui-audit.mjs` is adapted from UUPM's `design-audit.mjs`.
- **Hooks**: `cp-build` packet gains a UI section (tokens, top rules, or a warning when no
  design system exists); `cp-review` and `cp-analysis-design` point to the audit / the design
  system; `cp-orchestrator` has `ui-design` and `ui-audit` routes.

Rulings made while implementing (they changed the design):

- **The visual audit runs only with explicit `--visual`.** A cloned repo's
  `.context/ui/profile.json` must never execute on a plain `--audit` (security). Without the
  flag the status is `skipped (--visual not given)`. The report path is confined to the
  project root; the run is persisted to `.context/ui/visual-last.json` and `--record` never
  re-runs it; `ran` is only claimed from that file for a matching scope.
- **Verify cannot pass vacuously.** A deleted, renamed, excluded, ignored or non-UI file, a
  missing design system for `raw-color`, a viewport the report never exercised, or checklist
  evidence that is not an existing file inside the project is a `fail`, not a pass.
- **UTC-strict timestamps.** Times are UTC with offset; a verify record counts only if
  strictly later than `cp-build --start` (`ui_verify_after`), for the same BUG and rule.
- **Dismissals made after `--start` are ignored by verify**, so a BUG cannot be "fixed" by
  dismissing its candidate; `--finish` says why a verify was rejected.
- **A confirmed static finding must match a scanner candidate** at `--record` (by line or by
  snippet in the evidence); what the scanner cannot see is filed as `checklist:<id>`.
- Candidates the agent leaves unaddressed are listed as not verified and counted in the header.

**Second command-running exception.** `cp-ui --audit --visual` (and `--verify --visual`) runs
the single command declared as `visual_audit.command` in `.context/ui/profile.json`, opt-in per
call, with a timeout (default 120 s), in the live project tree; the packet prints the exact
command and cwd first. The command only opens the URL of an app the operator already started
and writes a report; the skill never starts or stops servers. CLAUDE.md rule 6 lists it next
to `cp-test --mutate` (ADR-0016).

**Consequences**: UI identity becomes an explicit, attributed, recorded decision, and UI
quality becomes a routed, non-blocking step that feeds the existing pipeline. Playwright and
Node are optional (the visual layer reports `not configured` without them). Trust model:
verify records and dismissals are plain files, **not tamper-proof**; they stop honest mistakes
and vacuous passes, not a determined forger, so `cp-review` shows `Re-checked by cp-ui` and
reviewers read them. Static checks are heuristics; false positives are dismissed with a reason
and remembered. Deferred: a screen x rule coverage ledger, refreshing the vendored data from
upstream, native-app visual audit, measuring the effect in `eval/`.
