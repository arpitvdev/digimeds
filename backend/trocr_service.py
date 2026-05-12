import torch
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from PIL import Image
import cv2
import pytesseract
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)


def preprocess_image(image_path):
    img = cv2.imread(image_path)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # strong contrast
    gray = cv2.convertScaleAbs(gray, alpha=2.0, beta=30)

    # sharpen
    kernel = np.array([[0, -1, 0],
                       [-1, 5,-1],
                       [0, -1, 0]])
    gray = cv2.filter2D(gray, -1, kernel)

    # threshold
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    return thresh


def trocr_ocr(image_path):
    image = preprocess_image(image_path)
    image = Image.fromarray(image).convert("RGB")

    pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)
    generated_ids = model.generate(pixel_values)

    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0]


def tesseract_ocr(image_path):
    img = preprocess_image(image_path)
    return pytesseract.image_to_string(img)


def clean_ocr_text(text):
    text = text.replace("—", "-")
    text = text.replace("l-o-l", "1-0-1")
    text = text.replace("l-o—!", "1-0-1")
    text = text.replace("Not logged in", "")
    text = text.replace("TalkContributions", "")
    return text


def trocr_ocr(image_path):
    image = preprocess_image(image_path)
    image = Image.fromarray(image).convert("RGB")

    pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)
    generated_ids = model.generate(pixel_values)

    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

def extract_text_from_prescription(image_path):
    trocr_text = trocr_ocr(image_path)
    tess_text = tesseract_ocr(image_path)

    combined = trocr_text + "\n" + tess_text
    combined = clean_ocr_text(combined)

    print("---- OCR TEXT ----")
    print(combined)

    return combined