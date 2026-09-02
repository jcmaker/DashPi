# Task 5 report: TypeScript protocol and fountain interoperability

## Implementation

- Added a strict TypeScript web package and lockfile.
- `parseFrame` decodes the DashPi Optical v1 wire layout and validates CRC, magic, version/flags, exact length, geometry, and indices before returning a copied symbol.
- `FountainDecoder` consumes carried indices (no shared PRNG), validates every input before mutation, bounds unresolved equations at 1024, deduplicates them, and rejects contradictory reduced or resolved equations.
- Tests use the committed Python golden fixture as the independent source of expected wire values.

## TDD record

RED — run from `web` after adding the test command and tests, before production modules:

```text
$ npm install && npm test
added 42 packages, and audited 43 packages in 3s
found 0 vulnerabilities
Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../web/src/optical/fountain.ts'
Error [ERR_MODULE_NOT_FOUND]: Cannot find module '.../web/src/optical/protocol.ts'
# fail 2
```

GREEN — run from `web` after minimal parser/decoder implementation:

```text
$ npm test
# tests 3
# pass 3
# fail 0
```

Boundary RED — run from `web` after adding the geometry test:

```text
$ npm test
not ok 4 - rejects a checksummed frame whose total length exceeds its geometry
error: 'Missing expected exception.'
# pass 3
# fail 1
```

Boundary GREEN — run from `web` after implementing geometry validation:

```text
$ npm test
# tests 4
# pass 4
# fail 0
```

Fountain conflict RED — run from `web` after adding the fully reduced conflict test:

```text
$ npm test
not ok 2 - rejects a conflicting equation that reduces to a solved block
error: 'Missing expected exception.'
# pass 4
# fail 1
```

Final GREEN — run from `web`:

```text
$ npm test && npx tsc --noEmit
# tests 8
# pass 8
# fail 0
```

Python contract check — run from repository root:

```text
$ .venv/bin/python -W error -m pytest tests/test_optical_protocol.py tests/test_optical_fountain.py -q
76 passed in 0.61s
```

## Files

- `.gitignore`
- `web/package.json`, `web/package-lock.json`, `web/tsconfig.json`
- `web/src/optical/protocol.ts`, `web/src/optical/fountain.ts`
- `web/tests/protocol.test.ts`, `web/tests/fountain.test.ts`

## Self-review and concerns

- Checked parser field offsets and CRC against `tests/fixtures/optical-v1.json`; no Decimen source, bytes, vectors, WASM, or artifacts were inspected.
- `node_modules` is ignored; no runtime dependency beyond the brief was added.
- The decoder intentionally caps unresolved equations at 1024; additional unique repair equations are ignored, so the caller can keep scanning valid frames without unbounded memory growth.
