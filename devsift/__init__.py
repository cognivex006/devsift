"""DevSift's read-only command interface."""
import sys

# Prevent subsequent imports from writing bytecode. Python may cache this
# initializer before it executes; use `python -B -m devsift` for a cold source
# checkout with a strict installation-tree no-write requirement.
sys.dont_write_bytecode = True
