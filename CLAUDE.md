# Working with Claude on srdatatools

`design_document.md` is the source of truth for scope, architecture, data model, and the phased **Feature to-do list**. When Emily names a to-do item (verbatim or paraphrased), that item is the unit of work.

## Picking up an item

- Treat the named item as the scope. Don't expand into neighboring checklist items or "while I'm here" cleanups — flag those as separate candidate items instead of doing them.
- Always start in Plan Mode, even for small items: explore relevant existing code/tests, propose an approach (data structures, key functions/modules per the design doc's module layout, test cases), and get explicit approval before writing any code.
- During planning, actively ask Emily about design decisions and tradeoffs relevant to the item rather than just presenting one proposed approach for yes/no approval — surface the decision points (edge cases, naming, structure, how a rule should behave) and ask for her view before settling on one, especially where the design doc doesn't already spell out the answer.
- Check the design doc's explicit out-of-scope list and phase boundaries before proposing an approach — don't pull forward later-phase work (e.g. don't wire in OpenAlex enrichment while doing a Phase 1 parser) without asking first.

## Implementation style

- **Data-handling code** (parsers, dedup/matching logic, merge/conflict-resolution logic): write test cases first or alongside the implementation, using realistic sample data (e.g. under `tests/data/`), covering normal cases and known vendor/format quirks called out in the design doc.
- **GUI/glue/wiring code**: implementation can come first; tests follow before the item is considered done.
- Work in logical steps (e.g. tokenizer, then field mapping, then tests, then wiring). One commit per step, short imperative commit messages matching existing history style.
- Check in after each step/commit-sized piece of work — don't run through an entire item silently.
- Never do visual/UI testing (launching the app, opening a browser, taking screenshots) — Emily does that herself. Never launch or drive a browser for this project for any reason without asking first and getting explicit go-ahead. Static checks (ruff, black, mypy, pytest) are fine and expected as usual.

## Coding style

- **Type hints:** full type hints on all functions and class attributes; mypy runs in CI and should pass clean.
- **Docstrings/comments:** minimal — rely on types and names to explain what code does. Only add a docstring or comment when it captures something not obvious from the signature (a tricky algorithm, a vendor quirk, a non-obvious constraint), per this project's general "no comments unless the why is non-obvious" default.
- **Formatting/linting:** black (formatting) + ruff (linting, import sorting), enforced via a pre-commit hook and in CI.
- **Data structures:** pydantic models for the core `Record` schema and other structures that parse/validate external or imported data (parser output, config). Use plain dataclasses for simple internal structures that don't need validation.

## Logging

- stdlib `logging`, module-level loggers (`logging.getLogger(__name__)`), configured once in `main.py`. Default to WARNING+ on the console; DEBUG available via a flag.
- Developer logging and the user-facing `activity_log` table are fully separate concerns. `activity_log` rows are plain-language records of actions written by the module performing the action (dedup, enrich, import, etc.) and are shown in the GUI. `logging.*` calls are for developers only — stack traces, malformed-data warnings, API errors — and never surface in the GUI.

## Error handling

- Use standard library exceptions (`ValueError`, `KeyError`, etc.); no custom exception hierarchy unless a specific case clearly needs one.
- Malformed/unexpected records during import (bad tag, missing required field, encoding issue): skip the bad record, log it and the reason, and continue importing the rest of the file. Surface a summary to the user (e.g. "998 imported, 2 skipped") rather than aborting the whole import.

## Naming conventions

- Standard PEP 8: `snake_case` for functions/variables, `PascalCase` for classes.
- Well-known acronyms (DOI, RIS, NBIB, etc.) are lowercased in identifiers, same as any other word: `record.doi`, `parse_ris()`.
- Test functions: `test_<unit>__<scenario>` (double underscore separates the unit under test from the scenario), e.g. `test_ris_parser__handles_multiline_abstract`, `test_dedup__exact_doi_match`.

## Branching

- Each to-do item gets its own branch, created off the latest `main` right after its plan is approved (before any code is written). Emily names the branch each time.
- Commit the item's logical steps to that branch as described above.
- When the item is done (tests passing, checkbox in `design_document.md` checked off), open a PR via `gh` for Emily to review/merge on GitHub — this is the merge path even for solo work, to keep a review checkpoint and PR history.
- Always ask before pushing the branch or opening the PR — never push or open a PR without explicit go-ahead, even once the item is otherwise complete.

## Definition of done

- Tests pass.
- Code matches the module layout in the design doc's Architecture section.
- The corresponding checkbox in `design_document.md`'s to-do list is checked off in the final commit for the item.
