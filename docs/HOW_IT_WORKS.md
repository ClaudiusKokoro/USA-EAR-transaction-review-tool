# How the tool works, and how EAR review works

[English](HOW_IT_WORKS.md) | [中文](HOW_IT_WORKS.zh.md)

This document has two halves:

- **Part 1** explains how the software is built and what happens to your data.
- **Part 2** explains how an EAR review is normally carried out, and which part
  of that work this tool does for you.

> This is engineering and process documentation, not legal advice. Nothing here
> states whether a particular transaction is authorised under the EAR.

---

# Part 1 - How the tool works

## 1.1 Design principles

| Principle | What it means in practice |
| --- | --- |
| **No legal conclusions** | The strongest automated statement is "this needs human review". The tool never says a transaction is legal, that no licence is required, or that the EAR has been violated. |
| **Facts before opinions** | Every step stores the facts you enter. Rules read those facts; they never edit them. |
| **Rules live in JSON** | Scores, thresholds, red flags and queue routing are data, not code, so a compliance team can tune them without touching Python. |
| **Local first** | Facts, reports, history and API keys stay on your machine. Network calls happen only when you click a button. |
| **Explainable** | Every awarded risk point is attributed to a named rule with an explanation, so a reviewer can audit the total. |
| **Screening never accuses** | A name match produces `MANUAL_VERIFICATION_REQUIRED`, never "restricted party". |

## 1.2 Architecture

```
Streamlit UI                       Application services                Data
────────────                       ────────────────────                ────
app/main.py  (workbench)  ─┐
                           ├──►  jurisdiction_service ─┐
app/ai_main.py (AI front) ─┘      deminimis_service    │
                                  fdp_service          │
                                  screening_service    ├──► rule_evaluator ──► app/rules/*.json
                                  enduse_service       │                        (safe expression engine)
                                  redflag_service      │
                                  risk_service         │
                                  report_service       ┘
                                       │
                                       ├──► ear_reviews.db        (local review history)
                                       ├──► HTML / PDF report
                                       └──► app/data/*.csv        (screening lists)
```

The services are plain Python functions with no Streamlit imports, which is why
the benchmark and the tests can drive the entire review pipeline without a
browser.

## 1.3 The review pipeline

| Step | Service | Input | Output |
| --- | --- | --- | --- |
| 1 Transaction intake | `models/transaction.py` | Parties, value, dates, destination | Validated facts |
| 2 Product information | `models/product.py` | Name, description, category, ECCN if known | Validated facts |
| 3 EAR jurisdiction | `jurisdiction_service` | Seven tri-state questions | `POSSIBLE_EAR_JURISDICTION` / `JURISDICTION_REVIEW_REQUIRED` / `INSUFFICIENT_INFORMATION` + reasons and missing facts |
| 4 De minimis | `deminimis_service` | Component rows (origin, controlled status, value, incorporated?) and total value | `COMPUTED` / `NO_CONTROLLED_US_CONTENT` / `MISSING_VALUE` / `MISSING_TOTAL` / `MISSING_INPUT` + ratio, exclusions and warnings |
| 5 FDP review | `fdp_service` | U.S. software/technology used, production chain facts | `POTENTIAL_FDP_ISSUE` / `NO_FDP_FACTS_IDENTIFIED` / `INSUFFICIENT_INFORMATION` + dependency map |
| 6 Party screening | `screening_service` | Party names and roles, local CSV lists | Per-party `MANUAL_VERIFICATION_REQUIRED` / `POSSIBLE_MATCH` / `NO_APPARENT_MATCH` with scores |
| 7 End use | `enduse_service` | Declared use, location, industry, use categories | End-use flags (military indicators, insufficient information, inconsistent activity, unclear location) |
| 8 Red flags | `redflag_service` | The flattened fact context | Triggered red flags with points and actions |
| 9 Risk engine | `risk_service` | Facts + red flags | Category scores (each capped), total 0-100, band |
| 10 Review queue | `risk_service` | Facts + score + red flags | Routing decision |
| 11 Report | `report_service` | The whole bundle | HTML and PDF, saved to local SQLite history |

## 1.4 The fact namespace

Before scoring, `risk_service.assemble_review_context()` flattens every step into
**one dictionary of simple facts**. Rules never reach into objects; they read
named values. This keeps the rule language safe and the rules readable.

Derived facts are computed for you, for example:

| Derived fact | How it is calculated |
| --- | --- |
| `has_eccn` | True when an ECCN is recorded and is not `unknown`/`n/a`/`none` |
| `existing_ear_status` | Normalised to `CONTROLLED`, `EAR99`, `NOT_US_ORIGIN`, `NOT_DETERMINED` or `UNKNOWN` |
| `product_military_terms` | Strong military vocabulary in the product name/description/category |
| `encryption_without_classification` | The description claims encryption/cryptography, no ECCN is recorded, and the wording is not negated |
| `destination_embargoed` | `ultimate_destination` is in the configured `US_EMBARGO` group |
| `buyer_country_embargoed` | `buyer_country` is in the same group (catches diversion risk) |
| `destination_special_attention` | Destination, or buyer country when the destination is missing, is in the `SPECIAL_ATTENTION` group |
| `has_us_content` | The jurisdiction answer says the foreign item contains U.S.-origin content |
| `de_minimis_computed` | A ratio exists (even 0%) |
| `fdp_potential` | The FDP step returned `POTENTIAL_FDP_ISSUE` |
| `screening_has_manual_verification` | Any party scored at or above 0.96 |
| `end_use_insufficient` and friends | The end-use step raised the matching flag |
| `red_flag_requires_legal` | At least one triggered red flag carries the action `LEGAL_REVIEW_REQUIRED` |

## 1.5 The rule engine

Rules are JSON, for example:

```json
{
  "rule_id": "RF003",
  "name": "Destination Under Comprehensive U.S. Embargo",
  "condition": "destination_embargoed == true",
  "risk_points": 25,
  "action": "LEGAL_REVIEW_REQUIRED",
  "explanation": "The ultimate destination is a country subject to a comprehensive U.S. embargo program."
}
```

Conditions are evaluated by a **whitelisted expression engine**
(`app/rule_evaluator.py`). It supports comparisons, `and`/`or`/`not`,
`in`, literals, and a fixed set of helpers (`lower`, `contains`, `isin`,
`coalesce`, `strip`, ...). Attribute access, indexing and arbitrary function
calls are rejected, and a rule that references an unknown field is reported as
a rule error instead of executing anything.

## 1.6 Scoring, bands and routing

1. **Red flags** fire first. Each carries points and an `action`.
2. **Risk categories** score independently and are capped. The caps must total
   100 (`app/rules/risk_rules.json`):

   | Category | Cap |
   | --- | --- |
   | EAR jurisdiction | 20 |
   | Product | 20 |
   | Destination | 15 |
   | End user | 20 |
   | End use | 10 |
   | Red flags | 15 |

3. **Bands**: LOW 0-20, MODERATE 21-40, ELEVATED 41-60, HIGH 61-80,
   CRITICAL 81-100.
4. **Routing** walks `app/rules/review_queue_rules.json` in order and the first
   match wins:

   | Order | Trigger | Decision |
   | --- | --- | --- |
   | RQ-01 | HIGH or CRITICAL | External counsel recommended |
   | RQ-02 | A party needs manual verification | External counsel recommended |
   | RQ-03 | Embargoed ultimate destination | External counsel recommended |
   | RQ-04 | ELEVATED | Legal review required |
   | RQ-05 | Jurisdiction flagged or insufficient | Legal review required |
   | RQ-06 | Potential FDP issue | Legal review required |
   | RQ-07 | A triggered red flag demands legal review | Legal review required |
   | RQ-08 | MODERATE, any red flag, possible name match, incomplete end use | Compliance review required |
   | RQ-09 | Default | Automated review complete |

## 1.7 Party screening

- Parties from Steps 1 and 6 are screened (exporter, buyer, consignee,
  ultimate end user, parent, subsidiary, director, beneficial owner).
- Each list is a CSV with the columns
  `name, aliases, country, reference, source, notes`. Multiple aliases are
  separated by `;`. Lines starting with `#` are ignored.
- Similarity combines character-level and token-level comparison, ignoring
  corporate suffixes such as *Ltd*, *LLC*, *GmbH*.
- Bands: **>= 0.96** manual verification, **0.65-0.96** possible match,
  **< 0.65** no apparent match.
- A match is a **lead, not a finding**: verify the legal entity, spelling,
  country, addresses and ownership before relying on it.

## 1.8 Screening list synchronisation

The **List & Data Center** downloads the official U.S. **Consolidated Screening
List** CSV published by the International Trade Administration, compares it with
your local snapshot, and shows what was added, removed or changed. Nothing is
overwritten until you confirm; applied data is written to
`app/data/ear_synced_lists.csv` and each run is logged in
`app/data/ear_sync_updates.csv`. No API key is required.

## 1.9 The AI assistant

The AI frontend is an assistant, not a decision maker:

- it talks to whichever provider you configure (OpenAI, Anthropic, DeepSeek,
  GLM, Qwen, Moonshot, Ollama or a custom OpenAI-compatible gateway);
- documents are parsed **locally** first, and providers with a Files API can
  also receive the original file;
- every review question is a standalone interface that asks **one** factual
  question at a time and records your answer into an exportable JSON draft;
- its system prompts repeat the same guardrails as the core tool.

Keys and per-provider settings are stored in `app/data/ai_config.json`, which is
git-ignored.

## 1.10 Reports, storage and quality control

- Step 11 produces an HTML report (11 sections, including the disclaimer) and a
  downloadable PDF, and saves the review to the local SQLite database
  `ear_reviews.db`.
- `pytest` covers every service, the models, persistence and the user interface
  (headless smoke tests).
- `benchmark/` runs 99 hand-authored transactions through the real pipeline and
  compares the outcome with rule-derived expectations, including guardrail
  assertions. It runs in CI on every push.

---

# Part 2 - How EAR review works, and how this tool maps to it

The EAR (15 CFR Parts 730-774) is administered by the U.S. Bureau of Industry
and Security. A normal review answers a chain of questions. The table shows
which ones this tool helps with, and where the tool deliberately stops.

## 2.1 Is the item subject to the EAR at all? (jurisdiction)

An item can fall within the EAR because it is in the United States, because it
is U.S.-origin and located abroad, because a foreign-made item contains more
than a de minimis share of controlled U.S. content, because it was produced with
certain U.S. technology or software, or because a U.S. person is involved in
the activity.

**Tool:** Step 3 asks `is_us_origin`, whether the foreign item contains U.S.
content, whether the values are known, whether U.S. software or technology was
used in production, and whether the production chain is known. It reports
`POSSIBLE_EAR_JURISDICTION`, `JURISDICTION_REVIEW_REQUIRED` or
`INSUFFICIENT_INFORMATION` - never "within" or "outside" the EAR. The tool does
not evaluate ITAR or other agencies' regimes; if a defence article may be
involved, the review must be redirected.

## 2.2 What is the item, and how is it classified? (ECCN / EAR99)

Items on the Commerce Control List carry an ECCN (for example `3A001`,
`5A002`, `5D002` for software), which encodes the category, the product group
(A systems, B test equipment, C materials, D software, E technology) and the
reasons for control. Items not on the CCL are EAR99.

**Tool:** Step 2 records the description, category and any existing ECCN or
status. If the description claims encryption capability without a recorded
ECCN, red flag `RF011` and risk rule `PRD-05` ask for classification. The tool
never assigns an ECCN.

## 2.3 Is a licence required?

Licence requirements come from the interaction of the classification, the
destination (Commerce Country Chart), the end use, the end user, and the General
Prohibitions in Part 736 - plus additional requirements triggered by lists such
as the Entity List or the Military End User List.

**Tool:** it does **not** determine licence requirements. It surfaces the facts
that drive them (classification status, destination group, end use, end user,
party screening) and routes the file to the right queue.

## 2.4 Do any licence exceptions apply?

Part 740 contains exceptions (for example TMP, RPL, GOV, ENC) with their own
conditions. Applying one is a legal judgement.

**Tool:** not modelled. The report keeps the question open for the reviewer.

## 2.5 End-use and end-user controls (Part 744)

Beyond the country chart, the EAR restricts exports for particular uses
(proliferation, military end use under 744.21, certain military-intelligence
end uses) and to particular users (Entity List, Military End User List,
Unverified List).

**Tool:** Step 7 records the declared use, installation location and industry,
and raises flags for military indicators, missing information, contradictory
activity and vague locations. Step 6 screens the parties. Neither step decides
that a control applies.

## 2.6 Restricted party screening

Consolidated screening lists include the BIS **Entity List**, **Denied Persons
List**, **Unverified List** and **Military End User List**, plus State and
Treasury lists. Good practice is to screen every party in the transaction,
including intermediaries, and to resolve hits by verifying identity against the
official source - never by name alone.

**Tool:** Step 6 screens the recorded parties against local CSV lists, including
the official list you synchronise with one click, and reports match scores with
the strongest possible result being `MANUAL_VERIFICATION_REQUIRED`.

## 2.7 Embargoed destinations and sanctions

Comprehensive embargo programmes (for example Cuba, Iran, North Korea, Syria)
sit largely with OFAC, but they also affect EAR analysis; BIS licence
requirements and policies vary by programme.

**Tool:** the destination groups in `app/data/country_data.json` drive red flag
`RF003` (ultimate destination), `DST-01`, and - for the buyer's own country -
`RF012` and `DST-04`. Both are configurable lists, not legal determinations.

## 2.8 De minimis (15 CFR 734.4)

For a foreign-made item that incorporates controlled U.S.-origin content, the
de minimis calculation compares the value of that controlled U.S. content with
the total value of the foreign-made item. Two points matter:

1. Only content **incorporated into** the item counts. U.S. software or
   technology used to *produce* the item belongs to the Foreign Direct Product
   analysis instead.
2. The threshold is not a single number. Commonly cited values are **25%** and,
   for certain ECCNs and destinations, **10%** - the rule text and the ECCN
   govern.

**Tool:** Step 4 sums the components whose origin is U.S. **and** whose
controlled status is controlled, divides by the total value, and reports the
ratio. Each component can be marked as incorporated or used in production only;
production-only rows are excluded and left to the FDP step. The tool scores the
magnitude (`JUR-05` 5-10%, `JUR-06` 10-25%, `JUR-07` >= 25%), warns about
inconsistent inputs, and **never states which threshold applies** - that is a
legal determination.

## 2.9 Foreign Direct Product rules (15 CFR 734.9)

Certain foreign-produced items are subject to the EAR because they were produced
with U.S. technology or software, or by a plant that is itself a direct product
of U.S. technology - the rules differ by programme (national security, 9x515 /
600 series, Russia/Belarus, advanced computing).

**Tool:** Step 5 asks what U.S. software, technology and equipment were used and
what the production chain looks like, then reports `POTENTIAL_FDP_ISSUE`,
`NO_FDP_FACTS_IDENTIFIED` or `INSUFFICIENT_INFORMATION` with a dependency map.
It never decides which FDP rule applies.

## 2.10 Red flags and due diligence

BIS publishes red-flag guidance: unusual routing, vague end use, cash payments
from unrelated third parties, reluctance to provide documentation, and so on.
Red flags are questions to resolve, not conclusions.

**Tool:** Step 8 evaluates the configurable red flags in
`app/rules/red_flag_rules.json` against the recorded facts. Each finding
carries points and a recommended **action** (for example
`OBTAIN_DE_MINIMIS_FACTS`, `COMPLETE_CLASSIFICATION`, `MANUAL_VERIFICATION_REQUIRED`,
`LEGAL_REVIEW_REQUIRED`), and the review queue reads those actions.

## 2.11 Documentation and escalation

An EAR review is only as good as its record: what was asked, what was answered,
what sources were checked, and who decided. Records must be kept and made
available on request.

**Tool:** every review produces a report with the facts, the triggered rules and
their explanations, the missing information, the queue decision and the
disclaimer, and stores it locally for later retrieval. When the queue says
`LEGAL_REVIEW_REQUIRED` or `EXTERNAL_COUNSEL_REVIEW_RECOMMENDED`, the file is
meant to go to a human - the tool has done its job at that point.

---

# Part 3 - Reading the output

| Output | Values | What it means | What to do |
| --- | --- | --- | --- |
| Jurisdiction | `POSSIBLE_EAR_JURISDICTION` | A U.S. nexus is recorded; jurisdiction cannot be excluded | Continue; classify the item |
| | `JURISDICTION_REVIEW_REQUIRED` | Facts point to a formal jurisdiction question | Have a specialist confirm |
| | `INSUFFICIENT_INFORMATION` | Key questions unanswered | Collect the missing facts |
| De minimis | `COMPUTED` | Ratio calculated | Legal review of the applicable threshold |
| | `NO_CONTROLLED_US_CONTENT` | Numerator is zero | Confirm the component data |
| | `MISSING_VALUE` / `MISSING_TOTAL` / `MISSING_INPUT` | Inputs missing (raises `RF010`) | Complete the calculation |
| FDP | `POTENTIAL_FDP_ISSUE` | U.S. inputs plus a production chain recorded | Legal review of the applicable FDP rule |
| | `NO_FDP_FACTS_IDENTIFIED` | No U.S. production inputs recorded | Confirm the production chain |
| | `INSUFFICIENT_INFORMATION` | U.S. inputs recorded but no production facts | Record facilities, equipment, process |
| Screening | `MANUAL_VERIFICATION_REQUIRED` (>= 0.96) | Strong name similarity | Verify identity against the official list |
| | `POSSIBLE_MATCH` (0.65-0.96) | Weaker similarity | Check spelling, entity and ownership |
| | `NO_APPARENT_MATCH` (< 0.65) | Below threshold | Keep the record |
| Risk | LOW / MODERATE / ELEVATED / HIGH / CRITICAL | Preliminary band from capped category scores | Read the itemised findings, not just the number |
| Queue | `AUTO_REVIEW_COMPLETE` | No threshold triggered | Keep the record |
| | `COMPLIANCE_REVIEW_REQUIRED` | Red flags or gaps to close | Compliance review |
| | `LEGAL_REVIEW_REQUIRED` | Legal question identified | Export-control attorney or specialist |
| | `EXTERNAL_COUNSEL_REVIEW_RECOMMENDED` | High severity, list match, embargo, or a legal-action red flag | External counsel |

---

# Part 4 - What the tool does not do

1. It does not decide **jurisdiction, classification, licence requirements,
   licence exceptions, de minimis thresholds or FDP applicability**.
2. It does not replace the **official lists**. A screening score is a lead; the
   Federal Register and the agencies' own publications govern.
3. It does not cover **ITAR, OFAC licensing, or other agencies' regimes**
   beyond providing configurable destination and sanctions-list data.
4. It does not evaluate **electronic delivery** differently from a physical
   shipment.
5. Its military and encryption detection is **keyword-based** and deliberately
   over-inclusive: it flags for review rather than deciding.
6. It is **not a substitute for counsel**. Every output is a preliminary work
   product.

---

# Part 5 - Glossary

| Term | Meaning |
| --- | --- |
| **BIS** | Bureau of Industry and Security (U.S. Department of Commerce) |
| **CCL / ECCN** | Commerce Control List / Export Control Classification Number |
| **CSL** | Consolidated Screening List (merged U.S. screening lists) |
| **De minimis** | Threshold test for controlled U.S. content in a foreign-made item |
| **DPL** | Denied Persons List |
| **EAR99** | Item subject to the EAR but not listed on the CCL |
| **Entity List** | Parties subject to additional licence requirements (Part 744) |
| **FDP** | Foreign Direct Product rule |
| **MEU** | Military End User (list and end-use control) |
| **OFAC** | Office of Foreign Assets Control (U.S. Department of the Treasury) |
| **UVL** | Unverified List |

## Official sources

- BIS: https://www.bis.gov/
- eCFR (15 CFR Parts 730-774): https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C
- Consolidated Screening List: https://www.trade.gov/consolidated-screening-list
- Federal Register (BIS notices): https://www.federalregister.gov/agencies/industry-and-security-bureau
