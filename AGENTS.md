# Working agreement

## Documentation

When writing documentation, optimise for the first-time reader. Write for the repository user, not the project maintainer.

- Write only what is true of the current system. No project history, superseded decisions, or phrases like "previously", "used to be", or "changed from".
- Do not document sessions, conversations, proposals, or abandoned ideas. They do not belong in the repository.
- When a decision changes, **rewrite** the affected text so it reads as though the new decision was always the decision. Do not annotate, strike through, or explain the change.
- Write as a product someone depends on. Avoid self-promotional framing and evaluative adjectives unless they describe a measurable property.
- Document stable behaviour and externally relevant design. Omit implementation details that are easier to understand from the code than from prose.
- Prefer concrete statements over qualifiers. Replace words like "typically", "generally", "usually", and "often" with precise descriptions whenever possible.
- Prefer describing the purpose of a step over describing what the command does.
- Do not turn README instructions into validation or test procedures.
- Prefer natural technical English over overly formal or specification-like wording.
- ADRs record decisions and the evidence behind them. Mention an alternative only when a reader might reasonably consider it and needs to understand why it was rejected.
- Routine refactoring, naming, code organisation, testing strategy, and local implementation choices do not require ADRs unless they create lasting architectural constraints.
- Keep each file focused on its primary purpose. Each file should answer the questions naturally associated with its purpose, and no others.
- Do not use configuration files, dependency manifests, or build files as surrogate documentation. Explanatory material belongs in README files or ADRs, not alongside declarative configuration.

## Comments and docstrings

Comments and docstrings exist to explain what the code cannot explain for itself. They should help future maintainers understand decisions, assumptions, and non-obvious behaviour.

- A module docstring should briefly describe the module's purpose. Document non-obvious behaviour only when it helps future maintainers.
- Do not restate signatures, imports, return values, or other code that the reader can already see.
- Explain why the code behaves this way, not how to read the implementation. Comments should explain decisions, assumptions, invariants, or surprising behaviour.
- Keep architectural rationale in ADRs or other architectural documentation rather than repeating it throughout the code.
- Avoid duplicating the same explanation in multiple places.
- Write plainly and directly. Avoid rhetorical or narrative wording.
- Prefer deleting an unnecessary comment over rewriting it.
- Comments describe the software, not the development process. Do not document experiments, investigations, measurements, or how the implementation was discovered unless that information is itself required to understand the code.

## Decisions

Record decisions as facts only when they are supported by evidence or explicit agreement.

- Present numbers, thresholds, and scope as settled only when they have been measured or explicitly agreed. Otherwise, treat them as open questions rather than resolved facts.
- If measurements contradict a number mentioned in conversation, say so and recommend the better-supported answer. Optimise for correctness, not agreement.
- Create an ADR for architectural decisions that introduce long-lived constraints or materially affect future development. Do not create ADRs for routine implementation details.
- Never infer implementation details to make documentation feel complete. If the repository or measurements do not establish a fact, leave it undocumented or explicitly mark it as an open question.
- Prefer omission over speculation. Documentation is allowed to be incomplete; it must not be inaccurate.
- Prefer concise explanations. Explain only what helps the reader understand or safely change the code.

## Tests

Tests should verify the current contract of the code, not its development history. If a requirement changes, update the contract and write tests against that contract. Avoid tests that exist only because a particular change happened during development; they document history rather than protecting behavior.

When changing Python code, run the relevant tests in the Astro Runtime container. Build the image with `docker build -t openaq-airflow:ci .`, then run either `docker run --rm openaq-airflow:ci python -m pytest tests -v` or a specific test module. Rebuild the image after changing the `Dockerfile` or `requirements.txt`.

Before committing Python changes, run Ruff in the Astro Runtime image: `docker build -t openaq-airflow:lint . && docker run --rm -v "$PWD":/workspace -w /workspace openaq-airflow:lint sh -lc 'python -m pip install --no-cache-dir ruff==0.15.22 && python -m ruff check .'`. Do not use a host installation of Ruff for this check.

## Git

- Never commit, push, or open a pull request without being asked. A change of topic is not approval.
- Never assume that creating commits is part of the requested task. Editing files does not imply permission to create Git history.
- Use Conventional Commits for commit messages, with a type such as `feat:`, `fix:`, or `chore:`.

## Configuration files

Keep configuration files concise and focused on current behaviour.

- Comments should explain intent, not implementation history or internal tool behaviour.
- Avoid comments that restate what the configuration already expresses.
- Prefer short section headers over narrative comments.
- Do not document version requirements, migration history, or architectural rationale in configuration files. Those belong in ADRs or other documentation.
- Keep `.gitignore` and `.dockerignore` organised into small logical sections with consistent naming.
- Ignore only what is necessary. Do not add defensive or speculative ignore rules without a concrete need.
- Configuration files should be self-explanatory. If understanding a setting requires a paragraph of explanation, the explanation belongs in documentation rather than inline comments.

## Python

Python version is pinned to 3.13.

- Do not add `from __future__ import annotations` unless it solves a concrete problem in that module. It should not be the default.
- Do not introduce helper functions unless they improve readability through meaningful abstraction or are reused.

## Markdown source

- Write one line per block: a paragraph, a list item, a table row, or a quoted paragraph each occupies a single line, however long. Do not hard-wrap prose at a column limit.
- Break a line only where the rendered output changes: between list items, between table rows, and around code fences. Leave code blocks exactly as written.
