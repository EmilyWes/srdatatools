# Contributing to srdatatools

Thanks for your interest in contributing! srdatatools is a local, open-source
tool for importing, merging, deduplicating, enriching, and exporting academic
paper metadata.

`design_document.md` is the source of truth for scope, architecture, the data
model, and the phased feature to-do list. Before starting work on something
non-trivial, please open an issue first (or comment on an existing one) so we
can agree on the approach — this avoids wasted effort on both sides.

## Getting set up

```bash
git clone <this repo>
cd srdatatools
python -m venv .venv
.venv/Scripts/activate     # .venv/bin/activate on macOS/Linux
pip install -e ".[dev]"
pre-commit install
```

`pre-commit install` sets up the git hook that runs black and ruff on staged
files before each commit.

## Running tests

```bash
pytest
```

Every parser and dedup rule should have tests covering it as it's written,
not bolted on afterwards. Data-handling code (parsers, dedup/matching,
merge/conflict-resolution logic) should use realistic sample data, kept under
`tests/data/`, covering both normal cases and known vendor/format quirks.

## Code style

- **Formatting:** [black](https://github.com/psf/black), enforced by
  pre-commit and CI.
- **Linting/import sorting:** [ruff](https://github.com/astral-sh/ruff),
  enforced by pre-commit and CI.
- **Type checking:** [mypy](https://mypy-lang.org/), enforced in CI. All
  functions and class attributes need full type hints.
- **Naming:** standard PEP 8 — `snake_case` for functions/variables,
  `PascalCase` for classes. Well-known acronyms (DOI, RIS, NBIB, etc.) are
  lowercased like any other word: `record.doi`, `parse_ris()`.
- **Comments/docstrings:** minimal. Rely on types and names to explain what
  code does; only add a comment or docstring when it captures something not
  obvious from the signature (a vendor quirk, a non-obvious constraint, a
  tricky algorithm).
- **Data structures:** pydantic models for the core `Record` schema and other
  structures that parse/validate external or imported data. Plain
  dataclasses for simple internal structures that don't need validation.
- **Errors:** standard library exceptions (`ValueError`, `KeyError`, etc.) —
  no custom exception hierarchy unless a case clearly needs one. During
  import, a malformed/unexpected record should be skipped and logged (with
  the reason), not abort the whole import.
- **Logging:** stdlib `logging` with module-level loggers
  (`logging.getLogger(__name__)`) for developer-facing messages (stack
  traces, malformed-data warnings, API errors). This is separate from the
  user-facing `activity_log`, which records plain-language descriptions of
  actions (import, merge, enrich, etc.) shown in the GUI — don't conflate
  the two.

## Tests

Test functions are named `test_<unit>__<scenario>`, e.g.
`test_ris_parser__handles_multiline_abstract`,
`test_dedup__exact_doi_match`.

## Commits and pull requests

- Keep commits scoped to one logical step, with short, imperative commit
  messages (e.g. "Add RIS tokenizer", not "added stuff for RIS parsing").
- Branch off the latest `main`.
- Open a pull request against `main` when ready for review. CI (tests,
  mypy, ruff, black) must pass before a PR is merged.
