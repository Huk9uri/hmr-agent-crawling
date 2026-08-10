# Task 6 Report: CLI, dry run, maximum-range backfill, and operational gate

## Status

Implemented with test-first RED/GREEN coverage and local-only verification. No
seller API was called, no production database connection was opened, and no
credential value was printed or copied into this worktree.

The authenticated dry runs, live boundary checks, database writes, SQL row
counts, one-latest-row checks, and `RawJson` PII sampling are intentionally
deferred to the post-review controller, as directed for this implementation
task.

## Delivered

- `list`, `collect`, and `collect-all` commands with explicit ISO dates.
- Dry-run behavior by default and a mutually exclusive `--write-db` gate.
- A strict registry that instantiates Naver, Coupang, Godomall, LotteON, 11st,
  SSG.COM, and Toss Shopping from one immutable config object. Missing any
  required channel credential fails configuration instead of silently omitting
  a channel.
- Inclusive window splitting for single-channel ranges and an initial
  `--maximum-window` range ending exactly on the supplied `--to` date.
- Conservative pre-live one-day policies for Godomall and 11st, pending the
  controller's authenticated boundary checks. The other current limits are
  Naver 1, Coupang 31, LotteON 1, SSG 180, and Toss 31 inclusive days.
- One collection-run UUID per channel write, with database writes delegated to
  the existing per-channel transactional `DatabaseWriter`.
- Count-only JSON summaries (`windows`, `records`, `inserted`, `changed`, and
  `skipped`) with status and exception type only. No records, response bodies,
  exception messages, PII, tokens, secrets, or database credentials are
  emitted.
- `--continue-on-error` channel isolation and a nonzero final exit code if any
  attempted channel fails. Without that flag, later channels are not called.
- A SQL Server connection factory using only `DB_SERVER`, `DB_NAME`, `DB_USER`,
  `DB_PASSWORD`, and optional validated `DB_PORT` values from strict config.
  Credentials are not accepted in argv and connection failures are sanitized.
- Exact Python 3.12 runtime dependencies in `requirements.txt`: requests
  2.32.5, bcrypt 5.0.0, and pymssql 2.3.13.
- A key-only `.env.example`, expanded cache/raw-response ignores, and operator
  documentation in `docs/channel-order-tables.md`.

## TDD evidence

- Initial RED: all 12 initial Task 6 tests failed because `cli.py`, the adapter
  registry, and the database connection factory did not exist.
- Database error-safety RED: a connection exception containing a server and
  password escaped before the production catch was added.
- Focused GREEN: all 13 Task 6 tests passed.
- Full repository GREEN: all 61 tests passed in 0.108 seconds using the pinned
  dependency set.
- CLI smoke test: `python -m hmr_order_collection.cli list` returned the seven
  expected channel names with exit code 0 and did not load config.

## Deferred controller-only operational verification

After independent code review, the controller should perform these steps in
order with its existing protected `.env` file:

1. Run authenticated read-only dry runs for all seven channels, with
   `--continue-on-error`, and record window/page/record counts and sanitized
   failure types.
2. Perform explicit invalid-period boundary checks for Godomall and 11st before
   changing their conservative one-day policies. Never infer a valid period
   from HTTP status alone.
3. Enable `--write-db` only for channels whose dry runs succeed.
4. Record inserted/changed/skipped counts and query SQL Server for per-channel
   row counts and the one-`IsLatest = 1` invariant.
5. Inspect masked `RawJson` samples by key classification, without exporting or
   logging record bodies, and verify that no unmasked PII key/value remains.

## Concerns

- Godomall and 11st maximum accepted periods remain an operational fact to
  establish with authenticated read-only responses; the implementation does
  not guess a wider period.
- The existing SSG ISO date serialization and 11st live XML variants remain
  explicitly assigned to credentialed dry-run verification.
