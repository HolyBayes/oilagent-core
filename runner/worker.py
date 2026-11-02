"""Container entrypoint. Candidate code is never imported by the host."""

import contextlib
import io
import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
request = json.loads(sys.stdin.readline())
namespace = {"__name__": "candidate"}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(request["source"], "candidate.py", "exec"), namespace)
    result = namespace["run"](request["input"])
sys.stdout.write(json.dumps(result, allow_nan=False))
