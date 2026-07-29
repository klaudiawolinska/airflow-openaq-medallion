# Working agreement

## Documentation

Every document in this repo is written for one reader: someone opening it for
the first time who needs to understand the system **as it stands now**.

- Write only what is true of the current system. No project history, superseded
  decisions, or phrases like "previously", "used to be", or "changed from".
- Do not document sessions, conversations, proposals, or abandoned ideas. They
  do not belong in the repository.
- When a decision changes, **rewrite** the affected text so it reads as though
  the new decision was always the decision. Do not annotate, strike through, or
  explain the change.
- Write as a product someone depends on. Avoid self-promotional framing and
  evaluative adjectives unless they describe a measurable property.
- Document stable behaviour and externally relevant design. Omit implementation
  details that are easier to understand from the code than from prose.
- Prefer concrete statements over qualifiers. Replace words like "typically",
  "generally", "usually", and "often" with precise descriptions whenever
  possible.

ADRs record decisions and the evidence behind them. Mention an alternative only
when a reader might reasonably consider it and needs to understand why it was
rejected.

Routine refactoring, naming, code organisation, testing strategy, and local
implementation choices do not require ADRs unless they create lasting
architectural constraints.

Keep each file focused on its primary purpose. Each file should answer the questions 
naturally associated with its purpose, and no others.

Do not use configuration files, dependency manifests, or build files as
surrogate documentation. Explanatory material belongs in README files or ADRs,
not alongside declarative configuration.

## Decisions

- Present numbers, thresholds, and scope as settled only when they have been
  measured or explicitly agreed. Otherwise, treat them as open questions rather
  than resolved facts.
- If measurements contradict a number mentioned in conversation, say so and 
  recommend the better-supported answer. Optimise for correctness, not agreement.
- Create an ADR for architectural decisions that introduce long-lived
  constraints or materially affect future development. Do not create ADRs for
  routine implementation details.
- Never infer implementation details to make documentation feel complete. If
  the repository or measurements do not establish a fact, leave it undocumented
  or explicitly mark it as an open question.
- Prefer omission over speculation. Documentation is allowed to be incomplete;
  it must not be inaccurate.
- Prefer omission over unnecessary explanation.

## Git

Never commit, push, or open a pull request without being asked. A change of
topic is not approval.

Never assume that creating commits is part of the requested task. Editing files
does not imply permission to create Git history.

## Configuration files

Keep configuration files concise and focused on current behaviour.

- Comments should explain intent, not implementation history or internal tool behaviour.
- Avoid comments that restate what the configuration already expresses.
- Prefer short section headers over narrative comments.
- Do not document version requirements, migration history, or architectural rationale in configuration files. Those belong in ADRs or other documentation.
- Keep `.gitignore` and `.dockerignore` organised into small logical sections with consistent naming.
- Ignore only what is necessary. Do not add defensive or speculative ignore rules without a concrete need.
- Configuration files should be self-explanatory. If understanding a setting requires a paragraph of explanation, the explanation belongs in documentation rather than inline comments.
