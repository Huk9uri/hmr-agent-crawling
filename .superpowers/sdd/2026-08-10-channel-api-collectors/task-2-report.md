# Task 2 report: date windows and collection history writer

## Files added

- `src/hmr_order_collection/channels/__init__.py`
- `src/hmr_order_collection/channels/base.py`
- `src/hmr_order_collection/database.py`
- `tests/test_windows.py`
- `tests/test_database.py`

## RED evidence

Before either production module existed, the required focused suite was run
with the bundled Python runtime:

```powershell
$env:PYTHONPATH = 'src'
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_windows tests.test_database -v
```

It failed as intended because both requested modules were absent:

```text
ModuleNotFoundError: No module named 'hmr_order_collection.channels'
ModuleNotFoundError: No module named 'hmr_order_collection.database'
Ran 2 tests in 0.000s
FAILED (errors=2)
```

## GREEN evidence

After the minimal implementations, the focused suite passed all ten cases:

```text
Ran 10 tests in 0.001s
OK
```

The final full-suite validation was run without bytecode writes:

```powershell
$env:PYTHONPATH = 'src'
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests -v
git diff --check
```

Observed result: `Ran 14 tests ... OK`; `git diff --check` exited zero.

## Implementation

- `DateWindow` and `iter_windows` produce inclusive, adjacent, non-overlapping
  windows, rejecting invalid ranges and non-positive maximum sizes.
- `ChannelAdapter` exposes the shared read-only `fetch(window)` contract.
- `DatabaseWriter` uses a static whitelist for the seven deployed table names,
  identity columns, and insertable columns. API-supplied column names outside
  that whitelist are rejected before SQL is executed.
- Every database value is passed through `%s` parameters. The writer applies
  SQL Server filtered-index session settings, starts one transaction, locks the
  current latest row with `UPDLOCK, HOLDLOCK`, skips an unchanged hash, or
  clears `IsLatest` and inserts a replacement history row.
- The fake connection test boundary verifies new, unchanged, changed, rollback,
  and identifier-injection behavior without opening a production connection or
  reading `.env`.

## Commit

`feat: add collection history writer`

## Concerns

No production database was contacted, by design. The writer accepts a
DB-API-compatible `pymssql` connection from its eventual CLI/bootstrap layer;
that connection configuration is intentionally outside this task so tests do
not load `.env` or credentials.
