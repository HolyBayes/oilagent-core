# Executable evolution: implementation in progress

The agreed target is a versioned native skill package containing instructions,
Python methods and parameters; a protected core owns contracts, data access,
evaluation, sandbox execution and release. This document records the current
implementation boundary, not completion of that target.

Implemented foundation:

- Python candidates use fixed capability slots and immutable Git commits. Main
  and installed skills remain unchanged. Source exports run(request).
- Packaging validation is not a Python sandbox: candidate execution uses a
  separate Docker image containing numerical dependencies and the worker only.
- The trusted executor uses a pinned local image digest, no network, no host
  mounts/socket, non-root user, read-only filesystem, dropped capabilities,
  CPU/RAM/PID limits, bounded input/output and a wall-clock deadline.
- Current candidate checks return CODE_EVALUATION_UNAVAILABLE. No executable
  candidate may pass critic or activate until protected evaluators are connected.

Verified using real Docker, without LLM calls: sum calculation, absence of core,
Docker socket and GigaChat credentials, and forced timeout of an infinite loop.
Worker image: sha256:d77fa3e7812f84aff109c04437c7188dfc1cbf5b459b55df46f96c0bfa46321c.

Still required: trusted executor service (without exposing Docker to author/MCP),
forecast/RAG/web implementations in evolution packages, protected paired metrics,
versioned candidate indexes, whole-package review/release with atomic pointer and
rollback, serving integration and full deployment checks. The existing running
service has not been switched to candidate Python execution.
