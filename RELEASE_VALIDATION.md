# Person A release validation

## Scope and provenance

The Person A adapter remains byte-for-byte at commit `37f04ee`.
B's `intelligence/` and `rag/` files are recovered unchanged from reviewed head
`e8ba64b62f8d2ccd1bd514a1a9673bb0407da6cc`. No PR merge or adapter replacement was
performed. Flask combines B's calls with the existing trusted identity, health,
startup and signed-confirmation controls. The frontend confirmation request now
includes the selected local fixture identity only in demo mode.

## Validation commands

Use `.venv/Scripts/python.exe` on Windows for the `python` commands below.

```text
python -m py_compile db_adapter.py app.py conftest.py wsgi.py intelligence/intent_engine.py intelligence/rbac.py intelligence/response_generator.py rag/retriever.py scripts/validate_real_reads.py tests/test_release_integration.py tests/test_mariadb_read_contract.py
python -m tabnanny db_adapter.py app.py intelligence rag tests scripts
git diff --check
python -m pytest --collect-only -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python -m pytest -q tests/test_db_adapter.py tests/test_production_boundary.py tests/test_release_integration.py -p no:cacheprovider
python -m pytest -q tests/test_mariadb_read_contract.py -p no:cacheprovider
python -m pip check
python scripts/validate_real_reads.py --student-id 917 --subject IT25201
```

Syntax, indentation, whitespace and installed dependency consistency checks pass.
Focused SQLite/Flask/boundary tests: 32 passed. Mocked MariaDB contract tests:
7 passed. Workspace regression: 39 passed, 28 skipped (26 legacy MariaDB tests
and 2 preserved untracked manual transaction tests). The release excludes that
untracked transaction test file, so its regression has 39 passed, 26 skipped.
A Google SDK deprecation warning on Python 3.14 is non-fatal.

Ordinary pytest forces SQLite before collection and rejects MariaDB/network
connections. Zero such connection attempts were observed. The two root manual
transaction probes are excluded by pytest.ini. No real ERP write was attempted.
SQLite write checks cover insert/update, duplicate idempotency, audit records,
and rollback when an audit insert fails.

## Live READ evidence and limits

The local Tailscale node reported Running/online. TCP, MariaDB authentication,
database selection, marks, subject attendance and timetable reads passed using
existing protected credentials. The known IAT1/IAT2 expectations passed. Each
validator connection explicitly uses a read-only MariaDB transaction mode.

Flask -> injected inference response -> B intent validation -> B RBAC/router ->
unchanged adapter -> real MariaDB passed for all three reads. Cross-student
access was denied. No credentials or academic records were emitted to logs.
Actual Gemma loading/inference was not exercised: the integration check stubs
only the model response through B's existing injection interface.

The repository defaults disable real DB mode, writes and initialization.
Tests cover trusted student identity, body-ID/role override rejection, missing
proxy mapping, signed/tampered/cross-user confirmations, reauthorization,
default-disabled real writes, policy/SQL separation and private-file denial.

## Remaining deployment/runtime work

- B supplies and verifies exact MLX-VLM/model versions and supported model-host
  OS/hardware. Google Gen AI 1.75.0 is installed/tested for import compatibility;
  no cloud client is automatically enabled.
- C validates actual voice/UI/model latency and deployed trusted proxy headers.
- B's teacher-to-class mapping remains intentionally fail-closed; no permission
  bypass or invented ERP role mapping has been added.
- Remote B/C connectivity, remote MariaDB host grants, firewall exposure and an
  actual production deployment are not certified by a localhost READ check.
- Real writes remain unapproved. The adapter's gated ERP write path has not been
  exercised; its audit/schema limitations remain documented in SCHEMA_MAPPING.md.

Existing manual probes/backups are preserved locally, unstaged and excluded from
this release. PR #2 and main are unchanged.
