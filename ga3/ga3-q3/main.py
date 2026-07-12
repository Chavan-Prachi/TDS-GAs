import os
from typing import Optional
from dateutil import parser as date_parser
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

# 5. Enable CORS for Cloudflare Worker / Grader
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Define Pydantic models for Request and Response
class InvoiceRequest(BaseModel):
    invoice_text: str

class InvoiceResponse(BaseModel):
    invoice_no: Optional[str] = None
    date: Optional[str] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None

# Initialize OpenAI Client (Ensure OPENAI_API_KEY is set in your environment)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 3. Helper function to parse any date string to YYYY-MM-DD
def parse_date_to_iso(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        # dateutil can parse "15 March 2026" automatically
        parsed_date = date_parser.parse(date_str, fuzzy=True)
        return parsed_date.strftime("%Y-%m-%d")
    except Exception:
        return None

@app.post("/extract", response_model=InvoiceResponse)
async def extract_invoice(request: InvoiceRequest):
    text = request.invoice_text
    
    try:
        # 2. Use LLM with Structured Output (JSON mode)
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini", # Cost-effective and highly capable
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "You are an expert invoice extraction assistant. Extract the fields from the invoice text.\n"
                        "Rules:\n"
                        "- 'invoice_no': The invoice number.\n"
                        "- 'date': The invoice date, strictly formatted as YYYY-MM-DD.\n"
                        "- 'vendor': The name of the vendor or company issuing the invoice.\n"
                        "- 'amount': The subtotal BEFORE any taxes are applied.\n"
                        "- 'tax': The exact tax amount ONLY (e.g., GST, VAT). Do not include this in 'amount'.\n"
                        "- 'currency': Infer from symbols (Rs./₹ -> INR, $ -> USD, € -> EUR). Default to INR if unclear.\n"
                        "- If any field is missing, return null for that key.\n"
                    )
                },
                {"role": "user", "content": text}
            ],
            response_format=InvoiceResponse, # Forces the LLM to output strictly matching this schema
        )
        
        extracted_data = completion.choices[0].message.parsed
        
        # Ensure date is strictly formatted to YYYY-MM-DD just in case
        if extracted_data.date:
            extracted_data.date = parse_date_to_iso(extracted_data.date)
            
        return extracted_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")