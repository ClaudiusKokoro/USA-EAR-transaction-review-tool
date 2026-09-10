# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
