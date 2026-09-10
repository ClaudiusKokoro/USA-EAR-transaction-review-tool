# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-09-10

### Fixed

Eight calibration problems found by the EAR review benchmark
(`benchmark/README.md` lists the case that locks in each fix):

- **De minimis was not graded.** A 6.7%, 60% or 160% U.S.-content ratio all
  scored the same. New rules `JUR-05`/`JUR-06`/`JUR-07` score the magnitude in
  three bands.
- **Incomplete de minimis data could auto-complete.** A controlled U.S.
  component with no value produced no red flag; new red flag `RF010` and risk
  rule `JUR-08` now route the review to compliance review.
- **Zero-value components were silent.** A controlled U.S. component recorded
  with value `0` is now excluded with a warning that names it.
- **Ratios above 100% were silent.** The calculator now warns when the U.S.
  content value exceeds the declared total value.
- **Red flag actions were ignored by the queue.** New queue rule `RQ-07` routes
  a transaction to legal review when a triggered red flag carries the
  `LEGAL_REVIEW_REQUIRED` action.
- **The red-flag category capped at 10 points.** The cap is now 15 (category
  maxima still total 100), so an embargoed destination reaches the ELEVATED
  band.
- **The embargo check ignored the buyer's country.** New red flag `RF012` and
  risk rule `DST-04` report a buyer located in a comprehensively embargoed
  country even when the ultimate destination is elsewhere.
- **Software handling was keyword-only.** Weak military terms (`guidance`,
  `targeting`, `radar`, `drone`, `uav`, `rocket`, `naval`, `camouflage`) now
  require a strong military term in the same text, and a shared
  `encryption_without_classification` fact drives new red flag `RF011` and risk
  rule `PRD-05` with negation handling.

### Added

- Long-form documentation: **`docs/HOW_IT_WORKS.md`** (with a Chinese edition at
  `docs/HOW_IT_WORKS.zh.md`) explains the architecture, the fact namespace, the
  rule engine, scoring, bands and routing, then walks through a real EAR review
  and states which parts the tool performs, which parts it only surfaces facts
  for, and what it never does.
- **EAR review benchmark** (`benchmark/`): 99 hand-authored cases with
  rule-based expectations, plus guardrail checks. CI runs it on every push.
- De minimis component rows can be marked **incorporated into the item** or
  **used in production only**; production-only rows are excluded from the
  numerator and belong to the FDP step.
- Red flag rules that fail to evaluate are reported as a rule error instead of
  aborting the whole red-flag step.

### Added

- Screenshots of the review workbench, party screening, list synchronization, and
  the AI assistant in both README files.

## [0.1.0] - 2026-09-10

First public release.

### Added

- **11-step EAR review workbench** (Streamlit): transaction intake, product
  information, jurisdiction review, de minimis calculator, FDP review, party
  screening, end-use review, red flag engine, risk engine, legal review queue,
  and report generator.
- **Configurable JSON rule sets** for red flags, risk scoring category weights,
  and review queue routing - no Python edits required to tune the model.
- **Party screening** against local CSV reference lists with exact matching,
  fuzzy name matching, and similarity scoring; the strongest possible result is
  `MANUAL VERIFICATION REQUIRED`.
- **List & Data Center** with a one-click "Sync latest EAR content" action that
  downloads the official U.S. Consolidated Screening List (CSL), diffs it
  against the local snapshot, shows added / removed / modified entries, and
  writes an applied snapshot plus an append-only change log.
- **Multi-provider AI assistant** supporting OpenAI (GPT), Anthropic (Claude),
  DeepSeek, Zhipu GLM, Qwen (DashScope), Moonshot, Ollama, and any custom
  OpenAI-compatible gateway, with local text extraction for uploaded documents.
- **15 standalone EAR question interfaces** that can prompt a model one
  question at a time and collect answers into an exportable JSON draft.
- **HTML and PDF reports** saved to a local SQLite review history.
- **Cross-platform launchers** for Windows (`*.bat`) and macOS/Linux
  (`*.sh`, `*.command`).
- **GitHub Actions CI** running the full test suite on Ubuntu, Windows, and
  macOS with Python 3.10 and 3.12.

### Security

- API keys, synchronized list files, SQLite databases, and report output are
  git-ignored; the repository ships only fictional sample screening data.
