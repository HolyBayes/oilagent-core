# Executable skill packages

Source methods live in the independent `evolution` Git repository:

```text
evolution/
  policies/{retrieval,web_sources}.json
  ouroboros_skills/
    oilgas_analyst/SKILL.md
    oil_forecast/{SKILL.md,forecast.py,scenario.py}
    report_rag/{SKILL.md,chunking.py,reranking.py}
    web_research/{SKILL.md,search_strategy.py}
```

All methods export `run(request)`. Core keeps data acquisition/cache, original
passages and citation metadata, input/output contracts, backtest targets,
calibration, fixed evaluators, credentials and operator release controls.
`core/src/analyst/seeds` contains the reproducible developer bootstrap; production
uses methods from an immutable release captured from evolution Git. Evolved
Python is never imported into Analyst, Evolution or the native agent process.

## Execution boundary

The private executor container has no host mounts, Docker socket or model secrets.
Its root filesystem is read-only. The trusted parent places each job in a private
scratch directory, enters an image-only chroot and drops to a fresh UID/GID before
loading candidate Python. The child gets only a small credential-free environment,
no `/proc`, evaluator, core, evolution checkout or service code. Seccomp denies
networking, process inspection, namespace changes and process-group escape.
The container has CPU/RAM/PID limits; the worker has resource limits and bounded
input/output. The parent enforces a wall-clock deadline and kills descendants.
One job executes at a time; up to four more wait for at most ten seconds within
their original deadline. Saturation fails closed. Worker diagnostics are bounded
untrusted text that the author can use to repair Python errors.
The common scratch parent is not writable/listable by workers; job directories
have mode 0700 and distinct owners. Scratch is discarded after every job.

Docker Desktop's current Linux kernel returns ENOSYS for Landlock, so confinement
uses mandatory chroot + UID separation + seccomp. Failure to enter the jail,
drop identity or install the filter stops execution. There is no unconfined mode.
Container isolation is not a claim of resistance to Linux kernel vulnerabilities.

The host deployment script builds the numerical image and pins its immutable local
image ID. The service does not control Docker. Executor identity is bound into
checks and releases. Run `python scripts/check_executor.py` explicitly for live
confinement/timeout/numerical-library checks, without any LLM calls.

## Checks and activation

`read_code(slot)` reads committed main. `propose_code` creates an immutable Git
candidate for one fixed method and increments its owning skill version. It cannot
change tests, data, contracts, release code or permissions. `run_checks` compares
with the **serving implementation**, using protected metrics and original targets:

- Forecast: ARIMA/ETS rolling metrics for two fixed windows, each horizon, MAE,
  coverage and interval width. Naive, targets and scoring remain in core.
- Chunking/reranking: supported source passages on the fixed PDF cases. Changed
  chunking builds an index under its implementation hash; serving index is untouched.
- Search strategy: ordering on fixed query/result cases, with provenance retained.
- Scenario: numerical equivalence on explicit fixed assumptions. The exact baseline
  already passes these cases; an equivalent rewrite does not manufacture improvement.

Checks require at least 1% gain and no individual regressions. They are fixed-case
measurements, **not a blind holdout or proof of general market accuracy**. A separate
critic reads the exact diff and metrics. Instruction-only candidates retain their
paired model tool-selection checks; policy candidates retain their PDF checks.
Failed/unavailable checks cannot approve or activate code. Repeated identical
checks are cached only while code, data, executor and serving baseline match.

The operator stages an immutable **whole package**, restarts native on that source,
requests native reviews for changed package hashes, then enables it. Admission is
blocked during this transition. All native skill hashes must match the frozen
files and have current executable reviews before the atomic serving pointer moves.
Each analytical request pins one set of method sources. The selected chunking hash
selects its matching prebuilt index. Main advances only at activation.

Rollback stages a previously reviewed package, follows the same native-source
transition, restores skill files in evolution main with a new commit, and atomically
switches methods/index. Unrelated files/policies survive. `abort` stages the active
source again and keeps admission blocked until native restart/enable completes.
An initial seed must finish native review; abort cannot open an unreviewed deployment.

## Recorded live checks

- [Executor confinement and resource limits](executor-evidence.json), no LLM calls.
- [Released HTTP forecast/PDF retrieval](package-mcp-evidence.json), no LLM calls.
- [Remaining method contracts](method-contracts-evidence.json), no LLM calls.
- [Zero-gain candidate](code-workflow-rejected.json) and
  [invalid-ABI candidate](code-workflow-invalid-abi.json): neither was activated.
- [GigaChat source with developer ABI repair](code-workflow-repaired.json):
  fixed ranking cases 1/3 to 3/3, no regressions, exact critic APPROVE.
- [Actual activation, rollback and restoration](code-release-cycle-evidence.json).
- [Separate full PDF index and zero-gain rejection](chunking-index-evidence.json).
- [All-method before/after runtime qualification](runtime-qualification-evidence.json).

Compact author/critic probes are not native UI author runs. Native review and
package activation were checked against the running UI. OpenAI/local live calls
remain intentionally untested; the optional Codex model bridge remains off.

CLI: `scripts/code_release.py seed|stage|review|enable|rollback|abort|status`.
Use `--operator` for mutations and exact `--sha` for candidate staging. Review can
make paid model calls; unchanged clean reviews are reused. Agent MCP has no release,
merge, enable, rollback, shell or direct file-write operation.
