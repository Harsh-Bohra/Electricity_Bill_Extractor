import streamlit as st
import google.generativeai as genai
import json
import os
import re
from datetime import datetime
import csv
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import pandas as pd
import zipfile
import tempfile
import time

# --- Config ---

# My Gemini API Key (hardcoded as requested)
API_KEY = "Enter yours here"

try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash-001")
except Exception as e:
    st.error(f"API Key error: {e}")
    st.stop()

# Optional: Configure Tesseract CMD if needed
# pytesseract.pytesseract.tesseract_cmd = r''

# --- Helper Functions ---

# Image preprocessing for OCR
def preprocess_image(image):
    image = image.convert("L") # Grayscale
    image = image.filter(ImageFilter.MedianFilter(size=3)) # Denoise
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(2.0) # Sharpen
    return image

# Date validation and normalization
def validate_and_normalize_date(date_str):
    if not date_str:
        return None
    formats = ['%d-%m-%Y', '%d-%b-%Y', '%d/%m/%Y', '%d.%m.%Y', '%Y-%m-%d', '%m/%d/%Y']
    cleaned_date_str = date_str.strip()
    for fmt in formats:
        try:
            date_obj = datetime.strptime(cleaned_date_str, fmt)
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None # Failed to parse

# Provider name normalization
def normalize_provider_name(provider_name):
    if not provider_name:
        return ""
    if re.search(r"adan", provider_name, re.IGNORECASE):
        return "Adani Electricity"
    return provider_name.strip()

# Field validation (returns data and errors)
def validate_fields(extracted_data):
    valid = True
    errors = []
    validated_data = extracted_data.copy()

    fields_to_check = [
        "Customer Name", "Customer Account Number / Consumer ID", "Billing Date",
        "Units Consumed (kWh)", "Amount Payable", "Due Date", "Tariff Category", "Electricity Provider Name"
    ]
    for field in fields_to_check:
        if field not in validated_data or validated_data[field] is None:
            validated_data[field] = ""

    for field in ["Units Consumed (kWh)", "Amount Payable"]:
        value_str = str(validated_data.get(field, "")).strip()
        if value_str:
            cleaned_value_str = value_str.replace(",", "")
            try:
                numeric_value = float(cleaned_value_str)
                if numeric_value < 0:
                    valid = False
                    errors.append(f"'{field}': Negative value found '{value_str}'.")
                validated_data[field] = numeric_value # Store as float if valid
            except ValueError:
                valid = False
                errors.append(f"'{field}': Invalid number format '{value_str}'.")

    for date_field in ["Billing Date", "Due Date"]:
        original_date_str = str(validated_data.get(date_field, "")).strip()
        if original_date_str:
            normalized_date = validate_and_normalize_date(original_date_str)
            if normalized_date:
                validated_data[date_field] = normalized_date
            else:
                valid = False
                errors.append(f"'{date_field}': Could not parse '{original_date_str}'.")
                validated_data[date_field] = original_date_str # Keep original invalid string
        else:
            validated_data[date_field] = ""

    if validated_data.get("Electricity Provider Name"):
        validated_data["Electricity Provider Name"] = normalize_provider_name(str(validated_data["Electricity Provider Name"]))
    else:
        validated_data["Electricity Provider Name"] = ""

    return validated_data, errors

# Adjust misplaced fields (specific logic from original script)
def validate_and_adjust_fields(extracted_data):
    account_key_string = "Customer Account Number / Consumer ID"
    if not extracted_data.get(account_key_string):
        for key, value in list(extracted_data.items()):
            if isinstance(value, str) and value.strip() == account_key_string:
                if not extracted_data.get(account_key_string):
                    extracted_data[account_key_string] = key
                    # Optional: del extracted_data[key]
                    break
    return extracted_data

# Process a single bill file
def process_single_bill(uploaded_file, bill_number, model, temp_dir):
    errors = []
    bill_name = uploaded_file.name
    validated_data = {} # Init empty

    try:
        # Save PDF to temp file
        temp_pdf_path = os.path.join(temp_dir, f"temp_bill_{bill_number}.pdf")
        with open(temp_pdf_path, "wb") as f:
            f.write(uploaded_file.getvalue())

        # PDF to image
        # Add poppler_path if needed: convert_from_path(..., poppler_path=r'<path>')
        images = convert_from_path(temp_pdf_path, first_page=1, last_page=1)

        if images:
            bill_image = images[0]
            processed_image = preprocess_image(bill_image)

            # Save image for OCR
            temp_image_path = os.path.join(temp_dir, f"temp_bill_{bill_number}_page_0.png")
            processed_image.save(temp_image_path)

            # OCR
            ocr_text = pytesseract.image_to_string(processed_image)

            # Prompt Gemini
            prompt = f"""
            Extract bill data as JSON: Customer Name, Customer Account Number / Consumer ID, Billing Date, Billing Period, Units Consumed (kWh), Amount Payable, Due Date, Tariff Category, Electricity Provider Name, Bill Number.
            Only return JSON. OCR Text: \"\"\"{ocr_text}\"\"\"
            """

            # Get Gemini response (with retries)
            max_retries = 3
            extracted_data = {}
            for i in range(max_retries):
                try:
                    response = model.generate_content(prompt)
                    json_match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
                    if json_match:
                        extracted_data_str = json_match.group(0)
                        extracted_data = json.loads(extracted_data_str)
                        break # Success
                    else:
                        errors.append(f"Attempt {i+1}: No JSON found in API response for '{bill_name}'.")
                        if i == max_retries - 1: errors.append(f"Failed JSON extraction for '{bill_name}'.")
                except json.JSONDecodeError as e:
                    errors.append(f"Attempt {i+1}: JSON decode error for '{bill_name}': {e}")
                    if i == max_retries - 1: errors.append(f"Failed JSON decode for '{bill_name}'.")
                except Exception as e:
                    errors.append(f"Attempt {i+1}: API/processing error for '{bill_name}': {e}")
                    if i == max_retries - 1: errors.append(f"Final error for '{bill_name}'.")
                time.sleep(1)

            # Adjust and validate
            adjusted_data = validate_and_adjust_fields(extracted_data.copy())
            validated_data, validation_errors = validate_fields(adjusted_data)
            errors.extend([f"Validation: {msg}" for msg in validation_errors])

            # Add Bill Number
            validated_data['Bill Number'] = f"Bill_{bill_number}"

        else:
            errors.append(f"PDF to image conversion failed for '{bill_name}'. Check Poppler install.")
            # Ensure empty data structure even on failure
            validated_data = {field: "" for field in ["Customer Name", "Customer Account Number / Consumer ID", "Billing Date", "Billing Period", "Units Consumed (kWh)", "Amount Payable", "Due Date", "Tariff Category", "Electricity Provider Name", "Bill Number"]}
            validated_data['Bill Number'] = f"Bill_{bill_number}"


    except Exception as e:
        errors.append(f"Unexpected error processing '{bill_name}': {e}")
        # Ensure empty data structure on critical error
        validated_data = {field: "" for field in ["Customer Name", "Customer Account Number / Consumer ID", "Billing Date", "Billing Period", "Units Consumed (kWh)", "Amount Payable", "Due Date", "Tariff Category", "Electricity Provider Name", "Bill Number"]}
        validated_data['Bill Number'] = f"Bill_{bill_number}"


    return validated_data, errors

# --- Streamlit UI ---

st.title("⚡ Electricity Bill Data Extractor")

st.write("Upload your electricity bill PDFs.")
st.info("Requires Tesseract OCR and Poppler.")

# Session state
if 'processed' not in st.session_state:
    st.session_state.processed = False
    st.session_state.results = []
    st.session_state.all_errors = []
    st.session_state.csv_output = None
    st.session_state.zip_output = None
    st.session_state.summary = {}

# File Uploader
uploaded_files = st.file_uploader("Upload Electricity Bill PDFs:", type="pdf", accept_multiple_files=True)

# Process & Clear Buttons
process_button = st.button("Process Bills")

if st.session_state.processed:
    clear_button = st.button("Process New Bills")
    if clear_button:
        st.session_state.processed = False
        st.session_state.results = []
        st.session_state.all_errors = []
        st.session_state.csv_output = None
        st.session_state.zip_output = None
        st.session_state.summary = {}
        st.experimental_rerun()

# Status messages
status_placeholder = st.empty()
error_placeholder = st.empty()

# --- Processing Logic ---

if process_button and uploaded_files and not st.session_state.processed:
    st.session_state.processed = True

    st.session_state.results = []
    st.session_state.all_errors = []
    st.session_state.csv_output = None
    st.session_state.zip_output = None
    st.session_state.summary = {}

    status_placeholder.info(f"Processing {len(uploaded_files)} bills...")
    progress_bar = st.progress(0)

    # Use temp directory for files
    with tempfile.TemporaryDirectory() as temp_dir:
        for i, uploaded_file in enumerate(uploaded_files):
            # Process each file
            extracted_data, errors_for_bill = process_single_bill(
                uploaded_file, i + 1, model, temp_dir
            )

            st.session_state.results.append(extracted_data)
            st.session_state.all_errors.extend(errors_for_bill)

            progress_bar.progress((i + 1) / len(uploaded_files))

        # --- Consolidation & Download Prep (Inside temp_dir block) ---
        if st.session_state.results:
            df = pd.DataFrame(st.session_state.results)

            # Save CSV to temp and read
            csv_filename = "consolidated_bills.csv"
            temp_csv_path = os.path.join(temp_dir, csv_filename)
            df.to_csv(temp_csv_path, index=False)
            with open(temp_csv_path, "rb") as f:
                st.session_state.csv_output = f.read()

            # Save JSONs to temp and zip them
            zip_filename = "all_bills_json.zip"
            temp_zip_path = os.path.join(temp_dir, zip_filename)
            temp_json_files_to_zip = []

            for i, data_row in enumerate(st.session_state.results):
                json_filename = f"bill_{i+1}_extracted.json"
                temp_json_path = os.path.join(temp_dir, json_filename)
                with open(temp_json_path, 'w') as json_file:
                    json.dump(data_row, json_file, indent=4)
                temp_json_files_to_zip.append(temp_json_path)

            with zipfile.ZipFile(temp_zip_path, 'w') as zipf:
                for json_file_path in temp_json_files_to_zip:
                    zipf.write(json_file_path, os.path.basename(json_file_path))

            with open(temp_zip_path, "rb") as f:
                st.session_state.zip_output = f.read()

            # Calculate Summary
            total_fields = len(st.session_state.results) * len(df.columns) if st.session_state.results else 0
            non_empty_fields = df.applymap(lambda x: x != "" and pd.notna(x)).sum().sum() if not df.empty else 0
            coverage = round((non_empty_fields / total_fields) * 100, 2) if total_fields > 0 else 0
            st.session_state.summary = {
                "Total Fields Across All Bills": total_fields,
                "Non-Empty Fields Extracted": non_empty_fields,
                "Extraction Coverage (%)": coverage
            }

            status_placeholder.success("Processing complete! Results ready.")

        else:
            status_placeholder.warning("No data extracted.")
            st.session_state.summary = {}

    progress_bar.empty() # Hide progress bar

elif process_button and not uploaded_files:
    error_placeholder.warning("Upload PDFs to start.")

# --- Display Results ---

if st.session_state.processed and st.session_state.csv_output is not None and st.session_state.zip_output is not None:
    st.subheader("Downloads")

    st.download_button(
        label="Download Consolidated CSV",
        data=st.session_state.csv_output,
        file_name="consolidated_bills.csv",
        mime="text/csv"
    )

    st.download_button(
        label="Download All JSON Files (Zip)",
        data=st.session_state.zip_output,
        file_name="all_bills_json.zip",
        mime="application/zip"
    )

    if st.session_state.summary:
        st.subheader("Summary")
        st.write(f"Total Fields: {st.session_state.summary['Total Fields Across All Bills']}")
        st.write(f"Non-Empty Fields: {st.session_state.summary['Non-Empty Fields Extracted']}")
        st.write(f"Coverage: {st.session_state.summary['Extraction Coverage (%)']}%")

    if st.session_state.all_errors:
        st.subheader("Notes/Errors")
        for msg in st.session_state.all_errors:
            st.warning(msg)

elif st.session_state.processed and (st.session_state.csv_output is None or st.session_state.zip_output is None):
    if st.session_state.all_errors:
        st.subheader("Notes/Errors")
        for msg in st.session_state.all_errors:
            st.warning(msg)
