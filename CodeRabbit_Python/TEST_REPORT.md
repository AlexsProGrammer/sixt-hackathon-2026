# CodeRabbit Python config test report

Tested: `coderabbit-python.yaml` against `sample_project/` (copied to a scratchpad temp dir; repo files not modified).
Environment: Python 3.15.2 in a temp venv with pyyaml, jsonschema, ruff, pytest (ruff and pytest were not preinstalled; PyYAML was installed in the venv). Python 3.11 is not available locally, so the `requires-python >=3.11` floor was NOT tested on 3.11 itself, only on 3.15.

## 1. Verified

### YAML validity and schema
- `python -I` with `yaml.safe_load`: parses OK. Top keys: language, early_access, reviews, chat.
- Schema downloaded from https://coderabbit.ai/integrations/schema.v2.json (needed `curl -L`, the first response was a 301; 86,209 bytes). Validated with jsonschema: 0 errors. The top level has `additionalProperties: false`, so there are no unknown keys at the top level, and no schema errors were reported deeper in the tree.

### Path globs (`**` as any depth, matched against the copy)
| Glob | Matches |
|---|---|
| `**/src/**/*.py` | src/inventory.py |
| `**/tests/**/*.py` | tests/test_inventory.py |
| `!**/.venv/**` | nothing |
| `!**/__pycache__/**` | only the pycache files that my own pytest run created in the copy; none in the original sample |
| `!**/*.ipynb_checkpoints/**` | nothing |
| `!**/data/**` | nothing |

The four exclusion filters match nothing in the sample project. That is expected for filters guarding against files that may appear later, but they are not exercised by this sample. Both `path_instructions` globs match their intended file.

### Ruff (`ruff check`, config from pyproject: select E, F, B, line-length 88)
Exit 1, 3 findings, all in src/inventory.py:
- F401 `os` imported but unused (line 1). Related rule: "no unused imports".
- B006 mutable default argument `items=[]` (line 5). Related rule: "no mutable default arguments".
- E722 bare `except` (line 15). Related rule: "no bare `except:`".

Notes: `json` is used, so only one unused import exists, not several. Ruff here uses the repo's pyproject selection. CodeRabbit's own Ruff run may use different defaults if it does not read pyproject.toml; this was not verified.

### Pytest
`pytest -q`: 1 passed (tests/test_inventory.py::test_1). Note the test passes only because the mutable default starts empty; it would be order-dependent if more tests called `add_item` without `items`.

### Rule coverage table
| Deliberate problem | Ruff | path_instructions (LLM) | Not covered |
|---|---|---|---|
| Mutable default (src) | Yes, B006 | Yes (src rule) | |
| Bare except (src) | Yes, E722 | Yes | |
| Unused import (src) | Yes, F401 | Yes | |
| TODO comment (src) | No (no T20/FIX rules selected) | No rule mentions TODOs | Not covered |
| Wrong docstring (`total_quantity` says "distinct items", sums qty) | No | Yes ("docstrings match the implementation") | |
| Missing type hints (src) | No (no ANN rules selected) | Yes ("type hints on public functions") | |
| Hardcoded key `API_KEY` (src) | No | Yes ("no secrets"); gitleaks is enabled, but whether it flags `sk-test-...` is unverified | |
| Weak test name `test_1` (tests) | No | Yes ("test names describe behaviour") | |
| No error-path tests (tests) | No | Yes ("cover ... error paths") | |

Only the TODO is not covered at all. Ruff and pytest cannot verify LLM-rule coverage; the "Yes" entries in the LLM column mean a matching instruction exists, not that CodeRabbit will flag the issue.

## 2. Expected but unverified
- The real CodeRabbit PR review (GitHub app) was not run. Whether the config is picked up requires it to be copied to the repo root as `.coderabbit.yaml`, as the header comment states.
- That the LLM will actually raise each issue in the table, and the quality of its comments.
- Whether gitleaks detects the placeholder-looking `sk-test-1234567890abcdef` key.
- That `auto_review` (base branch `main`, drafts off, WIP/DO NOT MERGE title skips) behaves as configured.
- That the exclusion filters work on real PR diffs.
- Behaviour on Python 3.11 exactly.

## Commands run
- `python3 -m venv <tmp>/venv; pip install pyyaml jsonschema ruff pytest`
- `cp -R sample_project/. <tmp>/copy/`
- `curl -sS -L -o schema.json https://coderabbit.ai/integrations/schema.v2.json`
- `python -I val.py schema.json coderabbit-python.yaml` (jsonschema validation) and `python -I chk.py` (yaml load plus glob matching, `**` translated to a regex)
- `ruff check .` and `pytest -q` in the copy
