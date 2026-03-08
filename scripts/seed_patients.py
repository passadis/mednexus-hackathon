"""Seed script – creates 3 sample patients and uploads mock medical files.

Usage:
    # Start the API first:  uvicorn mednexus.api.main:app --port 8000
    # Then:
    python scripts/seed_patients.py [--base-url http://localhost:8000]

What it does:
  1. Creates P001, P002, P003 via POST /api/patients/{id}
  2. Generates mock files in data/mock/ (X-rays, transcripts, PDFs)
  3. Uploads each file via POST /api/patients/{id}/upload
  4. The agent pipeline kicks in automatically for each upload
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

# ── Patient Definitions (from inputs/patients.txt) ──────────

PATIENTS = [
    {
        "id": "P001",
        "name": "John Mitchell",
        "label": 'The "Silent Pleurisy" (Respiratory)',
        "files": [
            {
                "filename": "P001_chest_xray.png",
                "description": "Chest X-ray showing right lower lobe opacification",
                "type": "image",
            },
            {
                "filename": "P001_interview_transcript.txt",
                "description": "Patient audio interview transcript",
                "type": "text",
                "content": (
                    "Patient Interview Transcript – P001 John Mitchell\n"
                    "Date: 2026-02-20\n"
                    "Interviewer: Dr. Sarah Chen\n\n"
                    "Patient states: \"I feel fine, just a little tired. No chest pain\n"
                    "really, maybe just a bit of a cough from the cold weather.\"\n\n"
                    "Vital signs: BP 138/88, HR 82, Temp 99.2°F, SpO2 96%\n"
                    "Observation: Patient appears mildly dyspneic on exertion.\n"
                    "History: 55 y/o male, history of mild asthma, non-smoker.\n"
                ),
            },
        ],
    },
    {
        "id": "P002",
        "name": "Emma Rodriguez",
        "label": 'The "Over-Active Athlete" (Orthopedic)',
        "files": [
            {
                "filename": "P002_knee_xray.png",
                "description": "Right knee X-ray, AP and lateral views",
                "type": "image",
            },
            {
                "filename": "P002_interview_transcript.txt",
                "description": "Patient audio interview transcript",
                "type": "text",
                "content": (
                    "Patient Interview Transcript – P002 Emma Rodriguez\n"
                    "Date: 2026-02-21\n"
                    "Interviewer: Dr. James Park\n\n"
                    "Patient states: \"My knee clicked during training. It hurts a lot,\n"
                    "I can't put weight on it. I'm worried it's an ACL tear.\"\n\n"
                    "Vital signs: BP 118/72, HR 68, Temp 98.6°F\n"
                    "Observation: Swelling and tenderness on palpation of right knee.\n"
                    "Positive Lachman test. Limited ROM due to pain.\n"
                    "History: 22 y/o female, professional soccer player.\n"
                ),
            },
            {
                "filename": "P002_medical_history.txt",
                "description": "Previous medical records",
                "type": "text",
                "content": (
                    "Medical History – P002 Emma Rodriguez\n"
                    "DOB: 2004-03-15 | Gender: Female | MRN: MRN-2002-0456\n\n"
                    "Previous Injuries:\n"
                    "  - 2024-01: Right meniscus repair (arthroscopic)\n"
                    "  - 2023-06: Left ankle sprain (Grade II)\n"
                    "  - 2022-11: Right knee contusion\n\n"
                    "Surgeries:\n"
                    "  - 2024-01-15: Arthroscopic partial meniscectomy, right knee\n"
                    "    Surgeon: Dr. Linda Zhao, Sports Medicine\n"
                    "    Recovery: 8 weeks, full return to play 2024-04\n\n"
                    "Allergies: None known\n"
                    "Medications: Ibuprofen PRN\n"
                ),
            },
        ],
    },
    {
        "id": "P003",
        "name": "Robert Chen",
        "label": 'The "Post-Op Palpitation" (Cardiac)',
        "files": [
            {
                "filename": "P003_chest_xray.png",
                "description": "Post-op chest X-ray with prosthetic valve visible",
                "type": "image",
            },
            {
                "filename": "P003_interview_transcript.txt",
                "description": "Patient audio interview transcript",
                "type": "text",
                "content": (
                    "Patient Interview Transcript – P003 Robert Chen\n"
                    "Date: 2026-02-22\n"
                    "Interviewer: Dr. Michelle Torres\n\n"
                    "Patient states: \"I'm feeling a fluttering in my chest when I lay\n"
                    "down. It's making me anxious. Is my new valve okay?\"\n\n"
                    "Vital signs: BP 128/78, HR 76 (irregular), Temp 98.4°F, SpO2 98%\n"
                    "Observation: Patient is alert, oriented, mild anxiety noted.\n"
                    "Surgical site healing well, no signs of infection.\n"
                    "History: 68 y/o male, 3 weeks post aortic valve replacement.\n"
                ),
            },
            {
                "filename": "P003_ecg_notes.txt",
                "description": "ECG interpretation and post-op cardiology notes",
                "type": "text",
                "content": (
                    "ECG Interpretation & Cardiology Notes – P003 Robert Chen\n"
                    "Date: 2026-02-22 | Cardiologist: Dr. Alan Nguyen\n\n"
                    "12-Lead ECG Findings:\n"
                    "  - Sinus rhythm at 76 bpm with occasional PVCs (3-4/min)\n"
                    "  - Normal axis, no ST changes\n"
                    "  - Prosthetic valve clicks present bilaterally\n\n"
                    "Assessment: Occasional PVCs noted but within normal\n"
                    "post-operative parameters. No evidence of valve dysfunction\n"
                    "or pericardial effusion on today's echo.\n\n"
                    "Plan: Continue current medication regimen (Warfarin 5mg,\n"
                    "Metoprolol 25mg BID). Tele-health follow-up in 1 week.\n"
                    "Reassurance provided re: benign nature of post-op PVCs.\n"
                ),
            },
        ],
    },
]


# ── Mock image generator ────────────────────────────────────


def _create_mock_xray(filepath: Path, label: str) -> None:
    """Generate a realistic-looking mock X-ray image using Pillow.

    Creates a 512x512 grayscale image with anatomical shapes and text labels
    so that GPT-4o Vision can meaningfully analyse it.
    """
    from PIL import Image, ImageDraw, ImageFont

    width, height = 512, 512
    img = Image.new("L", (width, height), color=20)  # dark background
    draw = ImageDraw.Draw(img)

    if "chest" in label.lower():
        # Draw torso outline
        draw.ellipse([130, 60, 380, 420], fill=40, outline=80, width=2)
        # Rib-like horizontal lines
        for y in range(120, 380, 35):
            draw.arc([140, y - 15, 300, y + 15], start=160, end=20, fill=70, width=1)
            draw.arc([210, y - 15, 370, y + 15], start=160, end=20, fill=70, width=1)
        # Heart silhouette (left-shifted)
        draw.ellipse([200, 200, 320, 340], fill=55, outline=90, width=2)
        # Right lower lobe opacity (pathology marker)
        draw.ellipse([150, 280, 230, 380], fill=75, outline=100, width=1)
        # Spine
        draw.line([(256, 60), (256, 420)], fill=80, width=6)
        # Clavicles
        draw.line([(150, 90), (256, 70)], fill=70, width=3)
        draw.line([(362, 90), (256, 70)], fill=70, width=3)

    elif "knee" in label.lower():
        # Femur (thigh bone)
        draw.rectangle([220, 20, 290, 240], fill=90, outline=110, width=2)
        # Femoral condyles
        draw.ellipse([200, 210, 260, 280], fill=80, outline=100, width=2)
        draw.ellipse([260, 210, 320, 280], fill=80, outline=100, width=2)
        # Joint space
        draw.rectangle([200, 270, 320, 285], fill=30)
        # Tibial plateau
        draw.ellipse([195, 275, 325, 320], fill=70, outline=100, width=2)
        # Tibia
        draw.rectangle([225, 310, 295, 490], fill=85, outline=110, width=2)
        # Patella
        draw.ellipse([235, 220, 275, 270], fill=100, outline=120, width=2)
        # Soft tissue swelling marker
        draw.ellipse([300, 230, 370, 310], fill=45, outline=60, width=1)

    else:
        # Generic X-ray: body outline with basic structures
        draw.ellipse([100, 30, 410, 480], fill=35, outline=70, width=2)
        draw.ellipse([200, 150, 310, 300], fill=55, outline=85, width=2)
        draw.line([(256, 40), (256, 470)], fill=75, width=4)

    # Add label text and metadata
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        font_small = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
        font_small = font

    draw.text((10, 10), "MEDNEXUS RADIOLOGY", fill=180, font=font)
    draw.text((10, 30), label[:60], fill=150, font=font_small)
    draw.text((10, height - 25), "MOCK MEDICAL IMAGE – FOR DEMO ONLY", fill=120, font=font_small)
    # Patient marker
    draw.text((width - 30, 10), "L", fill=200, font=font)

    img.save(str(filepath), "PNG")
    print(f"  📷 Created mock X-ray: {filepath.name}  ({label})")


# ── Seed logic ───────────────────────────────────────────────


def seed(base_url: str) -> None:
    mock_dir = Path(__file__).resolve().parent.parent / "data" / "mock"
    mock_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(base_url=base_url, timeout=30.0)

    for patient in PATIENTS:
        pid = patient["id"]
        name = patient["name"]
        print(f"\n{'='*60}")
        print(f"🏥 Patient {pid}: {name} — {patient['label']}")
        print(f"{'='*60}")

        # 1. Create patient
        resp = client.post(f"/api/patients/{pid}", params={"name": name})
        if resp.status_code == 201 or resp.status_code == 200:
            print(f"  ✅ Created patient {pid}")
        elif resp.status_code == 409:
            print(f"  ⚠️  Patient {pid} already exists — skipping creation")
        else:
            print(f"  ❌ Failed to create {pid}: {resp.status_code} {resp.text}")

        # 2. Generate & upload files
        for file_def in patient["files"]:
            filename = file_def["filename"]
            filepath = mock_dir / filename

            # Generate mock file if it doesn't exist yet
            if not filepath.exists():
                if file_def["type"] == "image":
                    _create_mock_xray(filepath, file_def["description"])
                else:
                    filepath.write_text(file_def["content"], encoding="utf-8")
                    print(f"  📄 Created mock file: {filename}")
            else:
                print(f"  📁 Using existing: {filename}")

            # Upload via API
            print(f"  ⬆️  Uploading {filename}...", end=" ", flush=True)
            with open(filepath, "rb") as f:
                resp = client.post(
                    f"/api/patients/{pid}/upload",
                    files={"file": (filename, f)},
                )

            if resp.status_code == 200:
                data = resp.json()
                print(f"✅ → {data.get('file_type', '?')} (task: {data.get('task_id', '?')[:8]}...)")
            else:
                print(f"❌ {resp.status_code}: {resp.text[:100]}")

            # Small delay to let agents process
            time.sleep(0.5)

    # 3. Summary
    print(f"\n{'='*60}")
    print("🎉 Seeding complete! Check the UI at http://localhost:5173")
    print(f"{'='*60}")

    # Show final status
    resp = client.get("/api/patients")
    if resp.status_code == 200:
        patients = resp.json()
        print(f"\nPatients in system: {len(patients)}")
        for p in patients:
            pid = p.get("patient", {}).get("patient_id", "?")
            status = p.get("status", "?")
            findings = len(p.get("findings", []))
            print(f"  {pid}: status={status}, findings={findings}")


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MedNexus with sample patients")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    print("🌱 MedNexus Patient Seeder")
    print(f"   Target: {args.base_url}")

    try:
        seed(args.base_url)
    except httpx.ConnectError:
        print(f"\n❌ Cannot connect to {args.base_url}")
        print("   Start the API first: uvicorn mednexus.api.main:app --port 8000")
        sys.exit(1)


if __name__ == "__main__":
    main()
