# CodeRabbit for Python: setup guide

Get automatic AI code review on your pull requests. The config in this folder is based on the Python examples in [awesome-coderabbit](https://github.com/coderabbitai/awesome-coderabbit/tree/main/configs/python) (`pytest-google-style-config.yaml` and `python-ruff-config.yaml`).

## What the config does

| Setting | Effect |
| --- | --- |
| `profile: chill` | Only reports important issues, less noise |
| `**/src/**/*.py` instructions | Google Python style, docstrings, type hints, no mutable defaults, no bare `except:`, no secrets |
| `**/tests/**/*.py` instructions | Pytest best practices, descriptive names, error-path coverage, deterministic tests |
| `tools: ruff, gitleaks` | Lint and secret scanning findings are included in the review |
| `auto_review` | Reviews PRs into `main`, skips drafts and PRs titled `WIP` or `DO NOT MERGE` |

## Step by step: configure it for your team

1. **Install the CodeRabbit GitHub app** on your fork (fork owner only): https://github.com/apps/coderabbitai. Choose "Only select repositories" and pick your fork.
2. **Copy the config to the repo root** under the name `.coderabbit.yaml`:
   ```bash
   cp CodeRabbit_Python/coderabbit-python.yaml .coderabbit.yaml
   ```
3. **Adjust paths** if your code is not under `src/` and `tests/`. The globs `**/src/**/*.py` and `**/tests/**/*.py` match any project folder, e.g. `Project_2/src/model.py`.
4. **Commit and push** the file to `main` of your fork.
5. **Open a pull request** inside your fork (for example from a team branch into your fork's `main`). CodeRabbit posts a summary and line comments within a few minutes.
6. **Talk to it** in the PR, for example `@coderabbitai explain this change` or `@coderabbitai review` to re-run.

## Try it on the sample project

[sample_project/](sample_project/) is a tiny Python app with deliberate problems: a mutable default argument, a bare `except`, an unused import, a TODO, a wrong docstring, a hardcoded key and a weak test name. Copy it to a branch, open a PR and see what CodeRabbit flags.

You can also check locally what the Ruff part will find:
```bash
cd CodeRabbit_Python/sample_project
pip install ruff pytest
ruff check .
pytest
```

## Validate your config

The first line of the YAML points to the official schema, so editors like VS Code (YAML extension) flag typos. A mistyped key is silently ignored by CodeRabbit, so validate before pushing.

## Tips

- Keep `.coderabbit.yaml` short. Add instructions only for things you care about.
- Never put secrets or real data in review instructions or code.
- Reviews apply only to repos where the app is installed. Nothing is reviewed until step 1 is done.

## Test agent

[.claude/agents/coderabbit-config-tester.md](../.claude/agents/coderabbit-config-tester.md) is a Claude Code agent that checks this config against the sample project (schema validity, path globs, Ruff findings, tests). See [TEST_REPORT.md](TEST_REPORT.md) for the latest run.
