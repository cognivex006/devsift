# Bounded trusted native processes

`run_process(ProcessSpec(...), stdin=b'', redactor=None)` executes exactly one
caller-configured program without a shell. `ProcessSpec` is frozen and requires
an absolute executable path, a tuple of literal argument strings, finite positive
wall timeout (default 10 seconds; maximum 3600), byte limits for each output stream
and stdin (default 1 MiB each; maximum 2,000,000 each), and an optional tuple of
explicit trusted environment key/value pairs. String command lines and Windows
batch/PowerShell script paths are rejected; `.bat`/`.cmd` can otherwise involve
implicit shell behavior even with shell=False. Resolve and pin executable identity,
version/integrity and program arguments in trusted adapter configuration; the
runner does not discover executables through PATH or target-project scripts.

```python
from devsift.process_runner import ProcessSpec, run_process

spec = ProcessSpec('/trusted/absolute/program', ('--version',), timeout_seconds=3)
result = run_process(spec)
```

`ProcessResult` is frozen and contains `status`, actual `exit_code` when available,
redacted UTF-8 `stdout`/`stderr`, and a fixed `reason`. Status is `completed` for
exit 0, `failed` for nonzero exit or runner/containment/redaction failure,
`unavailable` for a missing executable, `timeout`, or `output_limit`. Completion
describes process execution, never a quality-gate pass or native analyzer support.
Nonzero child stderr is captured through the accepted Redactor. Callers supply
known credential/sensitive values to that Redactor; its built-in patterns are
defensive masking, not a comprehensive secret detector. Specs omit executable,
argv and environment from repr; results omit both streams. Exceptions and results
never expose attempted command lines, source arguments, raw OS errors or stderr.

Independent drain threads read both pipes incrementally in 8192-byte chunks, with
separate capped buffers; a writer feeds bounded stdin concurrently. This avoids
the pipe deadlocks and unbounded capture of `communicate()`. The wall deadline
covers process execution and pipe completion, including descendants holding pipes
after the parent exits. On timeout/output limit or any partial I/O failure, both
raw streams are discarded entirely: truncation could expose part of a secret
that full-value redaction would otherwise mask. Cleanup adds a bounded wait/join
budget after the execution deadline. No CPU, child-memory or disk quota is claimed.

Each invocation creates and later cleans only its owned temporary directory,
outside the scanned target. It is the child's cwd and HOME/USERPROFILE/TMP
directory. The environment is rebuilt rather than inherited: fixed C locale, UTC,
Python no-bytecode/no-user-site/safe-path flags and a fixed system PATH; Windows
also uses the actual OS Windows directory. Ambient PYTHONPATH/PYTHONSTARTUP,
NODE_OPTIONS, DOTNET_STARTUP_HOOKS, GOFLAGS, LD_PRELOAD and other project hooks are
absent. Any additional variable is an explicit trusted caller allowlist choice,
which must not be populated from untrusted source-project environment settings.
The runner does not install dependencies, invoke builds, discover project hooks,
request network access, or use the target as a working directory.

On POSIX the child starts a new session; cleanup kills its owned process group.
On Windows it starts suspended, is assigned to a private kill-on-close Job Object,
then resumes through documented thread enumeration/OpenThread/ResumeThread APIs.
Assignment failure (including incompatible enclosing jobs) fails closed before
native execution. The runner terminates its job/group on completion as well as
failure, preventing ordinary detached descendants from surviving the invocation.
Cleanup also directly terminates and reaps the exact owned child if still alive:
a suspended child whose job assignment failed is not contained in the empty job.
Any failed wait triggers a further bounded direct-kill/reap attempt. Empty-job
termination success alone is never treated as proof that the child exited.
See Microsoft's [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
and [Toolhelp snapshots](https://learn.microsoft.com/en-us/windows/win32/toolhelp/snapshots-of-the-system)
for the Windows lifecycle primitives. The Windows tests actually exercise job
assignment, bounded output and descendant termination; Linux CI exercises sessions.

This is **not an OS security sandbox**. A trusted executable can access files or
network, consume CPU/memory, or deliberately escape a POSIX session/process group.
It must obey the adapter's read-only contract. The runner enforces time, capture
limits and ordinary process-tree cleanup; it cannot undo an executable's arbitrary
side effects. Abrupt host-process termination can bypass ordinary Python cleanup;
Windows kill-on-job-close adds OS cleanup once the child is assigned. Isolated
working directories and environment filtering do not authorize target writes.
