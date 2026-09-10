# Contributing

Thanks for considering a contribution. This project is a **local-first EAR
transaction review tool**, used by compliance and legal reviewers, so the bar
for correctness and for protecting user data is high.

## Before you start

Please read the guardrails in the README. In short:

- the tool **never** produces legal conclusions - no "this is legal", no "no
  license is required", no "this violates the EAR";
- party screening **never** outputs "restricted party"; the strongest result is
  `MANUAL VERIFICATION REQUIRED`;
- rule points are indicators for human review, not determinations.

Any change that breaks these properties will not be merged.

## Development setup

```bash
git clone https://github.com/ClaudiusKokoro/USA-EAR-transaction-review-tool.git
cd USA-EAR-transaction-review-tool

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest                             # 90+ tests, no network required
streamlit run app/main.py          # review workbench
streamlit run app/ai_main.py       # AI assistant
```

Tests must pass without network access. Anything that needs the internet (the
list sync download, LLM calls) is covered with injected fakes instead.

## What to change where

| You want to... | Edit |
| --- | --- |
| Adjust risk weights, red flags, or queue routing | `app/rules/*.json` |
| Add or reword a review question | `app/rules/ear_question_interfaces.json` |
| Add an LLM provider | `app/ai_frontend/providers.py` (+ tests) |
| Change screening behaviour | `app/services/screening_service.py` |
| Change the official list sync | `app/services/ear_list_sync_service.py` |
| Change the workflow UI | `app/main.py` |
| Change report output | `app/services/report_service.py`, `app/templates/report.html` |

Prefer configuration over code: if a reviewer can express the change in
`app/rules/*.json`, do that instead of editing Python.

## Coding guidelines

- Python 3.10+ (CI runs 3.10 and 3.12 on Linux, Windows, and macOS).
- The user interface is **English only**. Chinese fields in
  `ear_question_interfaces.json` are optional data for localized deployments.
- Keep the service layer free of Streamlit imports so it stays testable.
- Format values with `Decimal` where the existing code does, and keep the
  "explain every awarded point" property of the risk engine.
- Add or extend a test for every behavioural change. UI changes should keep
  `tests/test_ui_smoke.py` passing.

## Data hygiene (important)

- Never commit API keys. `app/data/ai_config.json` holds keys in plaintext and
  is git-ignored; keep it that way.
- Never commit real transaction data, SQLite databases (`*.db`), report output,
  or synchronized screening lists (`app/data/ear_synced_lists.csv`, ...).
- The bundled `app/data/restricted_parties.csv` must stay clearly labelled
  sample data. Do not add real restricted-party data to the repository.
- In issues and pull requests, replace real names with obvious placeholders.

## Pull requests

1. Fork the repository and create a topic branch.
2. Make the change, add tests, and run `pytest` locally.
3. Open a pull request using the template. CI runs the full suite on three
   operating systems and two Python versions.
4. Describe any user-visible change, and call out anything that touches
   compliance wording, so it can be reviewed carefully.

Keep commits focused and use clear messages, for example
`feat(screening): add alias matching for entity list entries` or
`fix(sync): handle an empty CSL download`.

## Reporting security issues

Please do not open a public issue for vulnerabilities - see
[SECURITY.md](SECURITY.md).
