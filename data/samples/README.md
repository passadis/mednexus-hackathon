# Sample Test Data

These files are provided for **hackathon judges** to test the full MedNexus agent pipeline without needing to source their own medical data.

## Files

| File | Type | What it triggers |
|---|---|---|
| `chest_xray.png` | Medical image | **Vision Specialist** — GPT-4o multimodal analysis with structured findings |
| `bloodwork.csv` | Lab results | **Clinical Sorter** — lab CSV classification and value extraction |
| `patient_transcript.txt` | Patient interview | **Patient Historian** — text extraction, RAG indexing, symptom analysis |
| `referral_letter.pdf.txt` | Referral document | **Patient Historian** — PDF text extraction and history synthesis |

## How to use

1. Open MedNexus and select (or create) a patient by typing a new name or patient ID (e.g. P037) and pressing Enter
2. Click **Upload** and drag in one or more of these files
3. Watch the **Agent Chatter** pane to see each agent process the files in real time
4. After all files are processed, the **Diagnostic Synthesis Report** will appear automatically

## What to look for

- The patient says *"no chest pain"* — but the X-ray may show findings that contradict this. The **Diagnostic Synthesis Agent** will flag the discrepancy.
- The bloodwork shows elevated WBC, ESR, and CRP (inflammatory markers) — which correlates with the imaging findings.
- The referral letter provides clinical context that the **Patient Historian** uses to build a longitudinal view.

## Note

You do **not** need to follow any file naming convention when uploading through the UI. The system automatically prefixes the patient ID. Just drag and drop.
