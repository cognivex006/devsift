"""Versioned command envelope and exit semantics, independent of analyzers."""
from enum import IntEnum


class Outcome(IntEnum):
    CLEAN = 0
    ENFORCED = 1
    INCOMPLETE = 2
    MISUSE = 3


def result(command: str | None, *, complete: bool, enforced_count: int = 0,
           findings: list | None = None, errors: list | None = None,
           data: dict | None = None) -> dict:
    """Incomplete takes precedence over enforced results; unknown is never clean.

    Callers must supply a verified enforced_count. This function does not classify
    findings or decide whether a finding is eligible for enforcement.
    """
    if type(complete) is not bool:
        raise ValueError('complete must be a boolean')
    if type(enforced_count) is not int or enforced_count < 0:
        raise ValueError('enforced_count must be a nonnegative integer')
    outcome = (Outcome.INCOMPLETE if not complete else
               Outcome.ENFORCED if enforced_count else Outcome.CLEAN)
    return {'schema_version': '1.0', 'command': command,
            'status': outcome.name.lower(), 'exit_code': int(outcome),
            'complete': complete, 'enforced_count': enforced_count,
            'findings': [] if findings is None else findings,
            'errors': [] if errors is None else errors,
            'data': {} if data is None else data}


def misuse(message: str) -> dict:
    record = result(None, complete=False,
                    errors=[{'code': 'INVALID_ARGUMENT', 'message': message}])
    record.update(status='misuse', exit_code=int(Outcome.MISUSE))
    return record
