import uvicorn
import os
import json
import time
import re
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore
from trocr_service import extract_text_from_prescription
from rapidfuzz import process

load_dotenv()

# ---------------- GEMINI ----------------
api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

# ---------------- FIREBASE ----------------
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

app = FastAPI(title="DigiMeds API 🚀")

# ---------------- LOAD DRUG DATABASE ----------------
with open("drug_database.json", "r") as f:
    DRUGS = json.load(f)

# ---------------- FUZZY MATCH ----------------
def correct_drug_name(name):
    if not name:
        return name

    match, score, _ = process.extractOne(name, DRUGS)

    if score > 70:
        return match

    return name

# ---------------- FILTER NON-MEDICINE ----------------
def is_valid_medicine(name):
    blacklist = ["brush", "toothbrush", "electric"]

    name_lower = name.lower()

    for word in blacklist:
        if word in name_lower:
            return False

    return True

# ---------------- DOSAGE EXTRACTION ----------------
def extract_dosage(text):
    match = re.search(r'\d+\s*mg', text.lower())
    if match:
        return match.group(0)
    return None

# ---------------- FREQUENCY NORMALIZATION ----------------
def normalize_frequency(freq):
    if not freq:
        return freq

    freq_clean = freq.replace(" ", "").replace("-", "").lower()

    mapping = {
        "101": "Twice daily",
        "111": "Thrice daily",
        "001": "Night",
        "bd": "Twice daily",
        "tds": "Thrice daily",
        "od": "Once daily"
    }

    for key, value in mapping.items():
        if key in freq_clean:
            return value

    return freq

# ---------------- GEMINI CALL ----------------
def call_gemini(image_path, ocr_text):
    for _ in range(3):
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": f"""
You are a medical prescription parser.

Use BOTH OCR text and image.

OCR TEXT:
{ocr_text}

Return ONLY valid JSON:
patientName, doctorName, prescriptionDate,
medications (drugName, dosage, frequency, duration)
"""
                            },
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image_bytes
                                }
                            }
                        ]
                    }
                ]
            )

            return response

        except Exception as e:
            print("Retrying Gemini...", e)
            time.sleep(2)

    raise Exception("Gemini failed")

# ---------------- MODELS ----------------
class Medication(BaseModel):
    drugName: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None

class Prescription(BaseModel):
    id: Optional[str] = None
    doctorName: Optional[str] = None
    patientName: Optional[str] = None
    prescriptionDate: Optional[str] = None
    medications: List[Medication] = []

# ---------------- AUTH ----------------
async def verify_token():
    return "demo_user"

# ---------------- ROUTES ----------------
@app.post("/scan")
async def scan_prescription(image: UploadFile = File(...)):
    try:
        file_path = f"temp_{image.filename}"

        # Save image
        with open(file_path, "wb") as buffer:
            buffer.write(await image.read())

        # OCR
        extracted_text = extract_text_from_prescription(file_path)

        print("OCR TEXT:", extracted_text)

        # Gemini
        response = call_gemini(file_path, extracted_text)

        response_text = response.text.strip()
        response_text = response_text.replace("```json", "").replace("```", "")

        result = json.loads(response_text)

        os.remove(file_path)

        # ---------------- POST PROCESS ----------------
        cleaned_meds = []

        for med in result.get("medications", []):
            name = med.get("drugName", "")

            # Remove unwanted items
            if not is_valid_medicine(name):
                continue

            # Correct name
            name = correct_drug_name(name)

            # Dosage
            dosage = med.get("dosage")
            if not dosage:
                dosage = extract_dosage(name)

            # Frequency
            freq = normalize_frequency(med.get("frequency"))

            cleaned_meds.append({
                "drugName": name,
                "dosage": dosage,
                "frequency": freq,
                "duration": med.get("duration")
            })

        result["medications"] = cleaned_meds

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------- RUN ----------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
