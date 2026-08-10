# Task 1 report: collector foundations

## Files added

- `src/hmr_order_collection/__init__.py`
- `src/hmr_order_collection/config.py`
- `src/hmr_order_collection/models.py`
- `src/hmr_order_collection/masking.py`
- `src/hmr_order_collection/http.py`
- `tests/__init__.py` (makes the `src` layout importable for the required direct unittest command)
- `tests/test_masking.py`

## RED

Command:

```powershell
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_masking -v
```

Observed output (expected):

```text
ModuleNotFoundError: No module named 'hmr_order_collection'
Ran 1 test in 0.001s
FAILED (errors=1)
```

The failure was caused by the package not existing, as required.

## GREEN

Command:

```powershell
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_masking -v
```

Observed output:

```text
test_masks_sensitive_nested_fields_but_preserves_order_and_product_identifiers ... ok
Ran 1 test in 0.000s
OK
```

## Final validation

```powershell
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m compileall -q src
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import sys; sys.path.insert(0, 'src'); import hmr_order_collection.config, hmr_order_collection.http, hmr_order_collection.masking, hmr_order_collection.models"
git diff --check
```

All completed successfully. The required unittest was also rerun after the final HTTP-helper refactor and remained green.

## Implementation summary

- Strict dotenv parser with immutable configuration values and no value logging.
- Frozen `ChannelRecord` model.
- Recursive sensitive-field masking, stable compact sorted JSON, and SHA-256 payload hashing.
- HTTP helper uses `(10, 60)` connect/read timeouts, retries 429 and all 5xx responses with a bounded attempt count, and raises body-free JSON/XML/HTTP errors.

## Commit

`feat: add collector foundations`

## Concerns

None. The source-layout test bootstrap was required because the repository has no packaging configuration and the brief requires invoking unittest directly from the worktree root.
