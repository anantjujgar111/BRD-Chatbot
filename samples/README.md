# Sample Input Files

Use these files to test the BRD chatbot upload and retrieval flow.

## Structured files

| File | Description |
|------|-------------|
| `excel/01_structured_functional_requirements.xlsx` | Clean requirements table with IDs, module, priority, owner, status |
| `excel/02_structured_stakeholders_matrix.xlsx` | Stakeholder matrix with role, department, influence |
| `excel/03_structured_non_functional_requirements.csv` | NFR list with targets and verification methods |

## Unstructured / messy files

| File | Description |
|------|-------------|
| `excel/04_unstructured_client_notes.xlsx` | Workshop notes, merged cells, scattered comments |
| `excel/05_unstructured_workshop_capture.xlsx` | Mixed layout, assumptions, out-of-scope notes, rough process |
| `excel/06_unstructured_legacy_export.xlsx` | Legacy dump with headers not on row 1 and random sections |

## Suggested test flow

1. Upload **all 6 files** together in the web UI.
2. Wait until each file shows status **indexed**.
3. Ask:
   - `What are the payment and refund requirements?`
   - `Who are the stakeholders and their influence levels?`
   - `What items are out of scope?`
4. Click **Generate Full BRD** and verify citations reference these files.

## Regenerate samples

```bash
source services/python-processor/.venv/bin/activate
python samples/generate_samples.py
```
