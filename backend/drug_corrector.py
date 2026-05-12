import json
from rapidfuzz import process

with open("drug_database.json") as f:
    drug_db = json.load(f)["drugs"]

def correct_drug_name(word):

    match = process.extractOne(word, drug_db)

    if match and match[1] > 80:
        return match[0]

    return word


def correct_text(text):

    words = text.split()

    corrected = []

    for w in words:
        corrected.append(correct_drug_name(w))

    return " ".join(corrected)