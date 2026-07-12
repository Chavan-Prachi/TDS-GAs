import re
import os
from typing import Optional
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

# Define Pydantic models
class InvoiceRequest(BaseModel):
    invoice_text: str

class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None

# Helper to clean and convert extracted amount strings to floats
def parse_amount(text: str) -> Optional[float]:
    if not text: return None
    # Remove commas, spaces, and currency symbols, keep only digits and dots
    clean_text = re.sub(r"[^\d.]", "", text)
    try:
        return float(clean_text)
    except ValueError:
        return None

@app.post("/extract", response_model=InvoiceResponse)
async def extract_invoice(request: InvoiceRequest):
    text = request.invoice_text
    
    # 1. Invoice No (Looks for Invoice No, Inv No, Invoice Number, etc.)
    inv_match = re.search(r"(?:Invoice|Inv)\s*(?:No|Number|#)?[:.\-]?\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    invoice_no = inv_match.group(1).strip() if inv_match else None

    # 2. Date (Looks for Date, Invoice Date)
    date_match = re.search(r"(?:Date|Invoice Date)[:.\-]?\s*([A-Za-z0-9\-/, ]+)", text, re.IGNORECASE)
    date_str = date_match.group(1).strip() if date_match else None
    date_iso = None
    if date_str:
        try:
            # dateutil automatically converts "15 March 2026" to "2026-03-15"
            date_iso = date_parser.parse(date_str, fuzzy=True).strftime("%Y-%m-%d")
        except Exception:
            date_iso = None

    # 3. Vendor (Looks for Vendor, From, Company, Seller, Billed By)
    vendor_match = re.search(r"(?:Vendor|From|Company|Seller|Billed By)[:.\-]?\s*(.+)", text, re.IGNORECASE)
    vendor = vendor_match.group(1).strip() if vendor_match else None

    # 4. Amount / Subtotal (Strictly looks for Subtotal, Total (excl. tax), etc. to avoid grabbing the Grand Total)
    amount_match = re.search(r"(?:Subtotal|Sub Total|Total \(excl\.? tax\)|Taxable Amount|Amount)[:.\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
    amount = parse_amount(amount_match.group(1)) if amount_match else None

    # 5. Tax (Looks for GST, VAT, Tax, CGST, SGST, IGST)
    tax_match = re.search(r"(?:GST|VAT|Tax|CGST|SGST|IGST)(?:\s*\(\d+%\))?[:.\-]?\s*(?:Rs\.?|₹|INR)?\s*([\d,]+\.?\d*)", text, re.IGNORECASE)
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