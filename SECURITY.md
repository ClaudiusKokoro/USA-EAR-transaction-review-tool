# Security Policy

## Supported versions

The latest release on the `main` branch is supported with security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting instead: open the repository's
**Security** tab and choose **Report a vulnerability**. If that option is not
available, contact the maintainer through their GitHub profile
([@ClaudiusKokoro](https://github.com/ClaudiusKokoro)).

Please include:

- what the issue is and why it is a security concern;
- steps to reproduce it;
- the affected version or commit;
- any suggested fix, if you have one.

You can expect an initial response within about a week. Please give us a
reasonable window to ship a fix before public disclosure.

## In scope

- Exposure or leakage of API keys stored by the tool
  (`app/data/ai_config.json`).
- Any way to make the tool send user data somewhere other than the provider or
  the official government endpoint the user configured.
- Code execution, path traversal, or file overwrite issues triggered by input
  files (documents, CSV screening lists, JSON rule files).
- Weaknesses in the rule evaluator that allow escaping the whitelist in
  `app/rule_evaluator.py`.
- Dependency vulnerabilities that affect the shipped code paths.

## Out of scope

- **Compliance or legal questions.** This project does not provide legal advice
  and does not determine whether a transaction is authorized under the EAR.
- **Accuracy or timeliness of government lists.** The tool downloads the
  official Consolidated Screening List; the authoritative sources remain the
  Federal Register and the issuing agencies.
- **A local user reading their own data.** Files under `app/data/` and
  `ear_reviews.db` are intentionally stored locally in plaintext.

## Data handling notes

- API keys are stored in plaintext in `app/data/ai_config.json` on the local
  machine only. That file is git-ignored; never commit it.
- Outbound network calls happen only when the user clicks a button:
  - the list sync downloads the official CSV from `data.trade.gov`;
  - AI requests go to the provider the user configured (which receives the API
    key, extracted document text, and the review summary the user entered).
- The bundled `app/data/restricted_parties.csv` contains fictional sample data
  only.

## Revoking a leaked key

If an API key or token was committed or shared by accident:

1. revoke it at the provider (OpenAI, Anthropic, GitHub, ...) immediately;
2. remove it from the working tree and from git history;
3. rotate any related credentials.
