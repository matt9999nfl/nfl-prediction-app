"""
Lets test modules in this directory use bare sibling imports (e.g.
`import snapshot_lines`) no matter which directory pytest is invoked from
or which other test files have already been collected in the same run.

scripts/__init__.py makes this directory a package, so pytest's default
import mode resolves a test module here as `scripts.test_x`, with
01-DATA-PIPELINE (not 01-DATA-PIPELINE/scripts) on sys.path -- one level
too high for a bare `import snapshot_lines` to resolve. A conftest.py is
always imported before any test file in its directory, regardless of
invocation order, which is what makes this fix order-independent (unlike
a sys.path.insert() inside one test file, which only happens to help its
siblings if pytest collects that file first).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
