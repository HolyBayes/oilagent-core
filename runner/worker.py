"""Container entrypoint. The parent sends the next input only after a result."""

import contextlib
import io
import json
import resource
import sys

resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
header = json.loads(sys.stdin.readline())
namespace = {"__name__": "candidate"}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(header["source"], "candidate.py", "exec"), namespace)
for line in sys.stdin:
    request = json.loads(line)
    with contextlib.redirect_stdout(io.StringIO()):
        result = namespace["run"](request)
    sys.stdout.write(json.dumps(result, allow_nan=False) + "\n")
    sys.stdout.flush()
