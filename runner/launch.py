"""Trusted launcher: enter the read-only jail, drop identity, then load code."""

import os
import resource
import sys

sys.path.insert(0, "/worker")
from restrict import restrict_syscalls

name, uid = sys.argv[1], int(sys.argv[2])
if not name.startswith("job-") or "/" in name or not 10000 <= uid <= 60000:
    raise ValueError("Invalid job identity")
os.chroot("/jail")
os.chdir("/tmp/" + name)
os.setgroups([])
os.setgid(uid)
os.setuid(uid)
if os.getuid() == 0 or os.path.exists("/proc"):
    raise RuntimeError("Worker confinement unavailable")
for limit, value in [
    (resource.RLIMIT_CPU, 110),
    (resource.RLIMIT_AS, 1024**3),
    (resource.RLIMIT_FSIZE, 1048576),
    (resource.RLIMIT_NOFILE, 64),
    (resource.RLIMIT_NPROC, 32),
]:
    resource.setrlimit(limit, (value, value))
restrict_syscalls()
os.execv(sys.executable, [sys.executable, "-I", "/worker/worker.py"])
