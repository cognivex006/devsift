"""Bounded explicit JSON input for commands; file contents are not authority."""
import json
import os
from pathlib import Path
import stat


class CommandInputError(ValueError):
    """Constant failure; never echo paths, JSON values or decoder exceptions."""


def _require(condition):
    if not condition:
        raise CommandInputError('Invalid or unavailable command input') from None


def _parents_regular(path):
    current=Path(path.anchor)
    for part in path.parts[1:]:
        current=current/part
        _require(not current.is_symlink() and not current.is_junction())
        if current.exists():
            _require(not (current.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                     if hasattr(current.lstat(),'st_file_attributes') else True)


def _pairs(items):
    value={}
    for key,item in items:
        _require(key not in value)
        value[key]=item
    return value


def _constant(_):
    _require(False)


def _bounded_tree(value):
    pending=[(value,0)]
    nodes=0
    while pending:
        item,depth=pending.pop()
        nodes+=1
        _require(nodes<=100_000 and depth<=64)
        children=item.values() if type(item) is dict else item if type(item) is list else ()
        _require(len(children)+nodes+len(pending)<=100_000)
        pending.extend((child,depth+1) for child in children)
    return value


def load_json_input(path, *, maximum_bytes=4_000_000):
    """Read one operator-selected regular file; no discovery, writes or execution.

    This rejects links and obvious path/descriptor changes, not a hostile
    same-user filesystem sandbox. Callers must separately reprove source and
    validate exact approval bindings; imported JSON grants no permissions.
    """
    descriptor=None
    try:
        _require(type(maximum_bytes) is int and 1<=maximum_bytes<=4_000_000)
        _require(isinstance(path,(str,Path)))
        selected=Path(path).absolute()
        _parents_regular(selected)
        before=selected.stat()
        _require(stat.S_ISREG(before.st_mode) and before.st_size<=maximum_bytes)
        flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
        descriptor=os.open(selected,flags)
        opened=os.fstat(descriptor)
        _require(stat.S_ISREG(opened.st_mode) and (opened.st_dev,opened.st_ino)==(before.st_dev,before.st_ino)
                 and opened.st_size<=maximum_bytes)
        with os.fdopen(descriptor,'rb') as stream:
            descriptor=None
            raw=stream.read(maximum_bytes+1)
            after=os.fstat(stream.fileno())
        _require(len(raw)<=maximum_bytes and len(raw)==opened.st_size
                 and (opened.st_size,opened.st_mtime_ns)==(after.st_size,after.st_mtime_ns))
        _parents_regular(selected)
        final=selected.stat()
        _require((final.st_dev,final.st_ino,final.st_size,final.st_mtime_ns)==
                 (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns))
        return _bounded_tree(json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant))
    except (OSError,ValueError,TypeError,RecursionError,OverflowError):
        raise CommandInputError('Invalid or unavailable command input') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
