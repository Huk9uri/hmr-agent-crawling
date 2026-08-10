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

## Fix round 1: review findings

### Files changed

- `.gitignore`
- `src/hmr_order_collection/http.py`
- `src/hmr_order_collection/models.py`
- `tests/test_http.py` (new)
- `tests/test_models.py` (new)

### RED regression command

```powershell
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_http tests.test_models -v
```

Observed output (expected):

```text
test_json_parse_error_redacts_query_fragment_and_user_info ... FAIL
test_request_exception_redacts_query_fragment_and_user_info ... FAIL
test_columns_cannot_be_mutated_after_record_construction ... FAIL
Ran 3 tests in 0.004s
FAILED (failures=3)
```

The request failure exposed its full secret-bearing URL, the JSON parser preserved user-info credentials in the URL, and a `ChannelRecord.columns` entry could be changed after construction.

### GREEN commands

```powershell
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_http tests.test_models -v
& 'C:\Users\user1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest -v
git check-ignore -q raw-responses/response.json
git check-ignore -q token-cache/access-token.json
git diff --check
```

Observed output:

```text
Focused regression suite: Ran 3 tests ... OK
Full unittest suite: Ran 4 tests ... OK
```

Both `git check-ignore` checks succeeded. The full-suite command is `python -m unittest -v`; `unittest discover -s tests` intentionally bypasses `tests/__init__.py`, which supplies the source-layout path, and therefore is not the appropriate command for this repository.

### Fixes

- All HTTP error paths now remove query strings, fragments, and user-info credentials from URLs before formatting exception messages.
- `ChannelRecord` defensively copies `columns` into an immutable `MappingProxyType` in `__post_init__`.
- Explicit raw-response and token-cache ignore patterns prevent those future artifacts from being staged.

### Chained-exception regression

The HTTP request test was extended so the underlying `ConnectionError` itself contains the secret-bearing URL. Before the final change it failed with:

```text
AssertionError: ConnectionError('connection refused: https://api-user:api-password@example.test/orders?access_token=top-secret#fragment') is not None
```

The request helper now suppresses that unredacted chained exception (`from None`). The focused suite and full suite commands above were rerun afterward and both passed (3 focused tests, 4 full-suite tests).
