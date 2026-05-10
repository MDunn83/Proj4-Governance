# Proj4 Governance Tool

An n8n workflow that reads user queries from Google Sheets, generates LLM responses via Groq, independently classifies both the query and the response for data governance, logs every result to an audit sheet, and routes sensitive or uncertain items to a human review queue.

---

## What It Does

1. Reads all rows from the **Questions** sheet (columns: `User ID`, `Query`)
2. Generates a plain-text LLM response for each query using Groq (`qwen/qwen3-32b`)
3. Classifies the **query** and the **response** independently and in parallel:
   - **Classification:** `SENSITIVE` | `STANDARD` | `UNCERTAIN`
   - **Domain:** `PII` | `FINANCIALS` | `STRATEGIC` | `CREDENTIALS` | `LEGAL` | `MEDICAL` | `HR` | `NAMED_INDIVIDUAL` | `NONE`
4. Appends every result to the **Audit Log Claude** sheet
5. Routes items where **either** the query class or the response class is `SENSITIVE` or `UNCERTAIN` to the **Review Claude** sheet

---

## Architecture

```
Manual Trigger
    └── Read Questions
            └── Set Start Time
                    └── Generate Response (Groq)
                            └── Strip Markdown
                                    ├── Classify Query (Groq) ──► Parse Query Result ──► Merge (input 0)
                                    └── Classify Response (Groq) ► Parse Response Result ► Merge (input 1)
                                                                                                └── Assemble Row
                                                                                                        └── Append Audit Log
                                                                                                                └── Route to Review (IF)
                                                                                                                        ├── [SENSITIVE/UNCERTAIN] Append Review
                                                                                                                        └── [STANDARD] No Operation
```

**Key design points:**
- Strip Markdown fans out to both classifiers simultaneously (true parallel execution)
- Merge node combines branches by position — each branch outputs uniquely named fields with no collisions
- All three Groq HTTP Request nodes use `batchSize: 1` / `batchInterval: 4000ms` to respect the free-tier 60 RPM limit
- `reasoning_effort: none` is set on all Groq calls to suppress qwen3 thinking blocks

---

## Output Columns

Both **Audit Log Claude** and **Review Claude** receive the same columns:

| Column | Description |
|---|---|
| Timestamp | ISO 8601 timestamp of when the row was written |
| User ID | From the Questions sheet |
| query | The original user query |
| response | LLM-generated plain-text response |
| response class | SENSITIVE / STANDARD / UNCERTAIN |
| response domain | Governance domain of the response |
| query class | SENSITIVE / STANDARD / UNCERTAIN |
| query domain | Governance domain of the query |
| input tokens | Total prompt tokens across all three LLM calls |
| output tokens | Total completion tokens across all three LLM calls |
| latency ms | Wall-clock time from Set Start Time to Assemble Row |
| est cost | Always 0 (Groq free tier) |

---

## Setup

### Prerequisites

- n8n instance (cloud or self-hosted)
- Google Sheets OAuth2 credential configured in n8n
- Groq API key configured as a Bearer Auth credential in n8n

### Google Sheets

The workflow targets spreadsheet ID `1HmqDSsCl35B9Nv9Fp4tJUhQdVJjAh3aGdKQeTV_Vat4`. Create or verify the following sheets:

| Sheet name | Required columns |
|---|---|
| Questions | `User ID`, `Query` |
| Audit Log Claude | See output columns above |
| Review Claude | See output columns above |

### Import Steps

1. In n8n, go to **Workflows → Import** and upload `proj4_governance_workflow.json`
2. Open each HTTP Request node and re-select your Groq Bearer Auth credential
3. Verify the Google Sheets nodes are using your **Google Sheets OAuth2 API** credential
4. Open the **Route to Review** IF node and confirm all four conditions show as expressions (not static values) — see known issues below
5. Save and run via the Manual Trigger

---

## Credentials

| Node | Credential type | Expected name |
|---|---|---|
| Read Questions | Google Sheets OAuth2 | `Google Sheets OAuth2 API` |
| Append Audit Log | Google Sheets OAuth2 | `Google Sheets OAuth2 API` |
| Append Review | Google Sheets OAuth2 | `Google Sheets OAuth2 API` |
| Generate Response | HTTP Bearer Auth | your Groq Bearer Auth credential |
| Classify Query | HTTP Bearer Auth | your Groq Bearer Auth credential |
| Classify Response | HTTP Bearer Auth | your Groq Bearer Auth credential |

---

## Known Issues

**IF node conditions on import** — n8n sometimes imports IF node conditions with the left side as a static value instead of an expression. If the workflow runs but all items go to the STANDARD branch regardless of classification, open the Route to Review node and manually re-enter the four conditions as expressions:
- `{{ $json['response class'] }}` equals `SENSITIVE`
- `{{ $json['response class'] }}` equals `UNCERTAIN`
- `{{ $json['query class'] }}` equals `SENSITIVE`
- `{{ $json['query class'] }}` equals `UNCERTAIN`
- Combinator: **OR**

---

## Files

| File | Description |
|---|---|
| `proj4_governance_workflow.json` | n8n workflow export — import this into n8n |
| `validate_workflow.py` | Validation script used during development |
| `LESSONS_LEARNED.md` | Build notes and gotchas for future n8n/Groq workflows |
| `n8n_SKILL(1).md` | n8n build rules reference used by Claude Code |
