import re
import os
from typing import Optional, Union
from dateutil import parser as date_parser
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS for Cloudflare Worker / Grader
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InvoiceRequest(BaseModel):
    invoice_text: str

class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    # Using Union[int, float] so 5600 returns as 5600, not 5600.0
    amount: Optional[Union[int, float]] = None
    tax: Optional[Union[int, float]] = None
    currency: Optional[str] = None

def parse_amount(text: str):
    if not text: return None
    # Remove everything except digits, commas, and dots
    clean_text = re.sub(r"[^\d.]", "", text)
    try:
        val = float(clean_text)
        # Return integer if it's a whole number (e.g., 5600 instead of 5600.0)
        return int(val) if val.is_integer() else val
    except ValueError:
        return None

@app.post("/extract", response_model=InvoiceResponse)
async def extract_invoice(request: InvoiceRequest):
    text = request.invoice_text
    
    # 1. Invoice No (Looks for Invoice No, Inv No, Invoice Number, etc.)
    inv_match = re.search(r"^\s*(?:Invoice|Inv)\s*(?:No|Number|#)?[:.\-]?\s*([A-Za-z0-9\-/]+)", text, re.IGNORECASE | re.MULTILINE)
    invoice_no = inv_match.group(1).strip() if inv_match else None

    # 2. Date (Looks for Date, Invoice Date, Bill Date, etc.)
    date_match = re.search(r"^\s*(?:Date|Invoice Date|Bill Date|Dated)[:.\-]?\s*([A-Za-z0-9\-/, ]+)", text, re.IGNORECASE | re.MULTILINE)
    date_str = date_match.group(1).strip() if date_match else None
    date_iso = None
    if date_str:
        try:
            date_iso = date_parser.parse(date_str, fuzzy=True).strftime("%Y-%m-%d")
        except Exception:
            date_iso = None

    # 3. Vendor (Looks for Vendor, From, Company, Seller, Supplier, etc.)
    vendor_match = re.search(r"^\s*(?:Vendor|From|Company|Seller|Billed By|Supplier|Bill From)[:.\-]?\s*(.+)", text, re.IGNORECASE | re.MULTILINE)
    vendor = vendor_match.group(1).strip() if vendor_match else None

    # 4. Amount / Subtotal (Highly robust regex)
    # First, try to find explicit subtotal keywords at the start of a line
    subtotal_pattern = r"^\s*(?:Sub[- ]?total|Total\s*\(?(?:excl\.?|excluding)\s*(?:tax|GST|VAT)\)?|Total\s*before\s*tax|Taxable\s*(?:Amount|Value)|Base\s*Amount|Assessable\s*Value|Net\s*Amount|Amount)[:.\-]?\s*(?:Rs\.?|₹|INR|USD|\$|€)?\s*([\d,]+\.?\d*)"
    amount_match = re.search(subtotal_pattern, text, re.IGNORECASE | re.MULTILINE)
    
    # Fallback: If no explicit subtotal keyword is found, look for "Total" (avoids "Grand Total")
    if not amount_match:
        total_pattern = r"^\s*Total[:.\-]?\s*(?:Rs\.?|₹|INR|USD|\$|€)?\s*([\d,]+\.?\d*)"
        amount_match = re.search(total_pattern, text, re.IGNORECASE | re.MULTILINE)
        
    amount = parse_amount(amount_match.group(1)) if amount_match else None

    # 5. Tax (Looks for GST, VAT, Tax, CGST, SGST, IGST, even if preceded by words like "Total Tax")
    tax_pattern = r"^\s*(?:.*?\s)?(?:GST|VAT|Tax|CGST|SGST|IGST)(?:\s*\(\d+%\))?[:.\-]?\s*(?:Rs\.?|₹|INR|USD|\$|€)?\s*([\d,]+\.?\d*)"
    tax_match = re.search(tax_pattern, text, re.IGNORECASE | re.MULTILINE)
    tax = parse_amount(tax_match.group(1)) if tax_match else None

    # 6. Currency (Infers from symbols, defaults to INR)
    if re.search(r"Rs\.?|₹|INR", text, re.IGNORECASE):
        currency = "INR"
    elif re.search(r"\$|USD", text):
        currency = "USD"
    elif re.search(r"€|EUR", text):
        currency = "EUR"
    else:
        currency = "INR" 

    return InvoiceResponse(
        invoice_no=invoice_no,
        date=date_iso,
        vendor=vendor,
        amount=amount,
        tax=tax,
        currency=currency
    )