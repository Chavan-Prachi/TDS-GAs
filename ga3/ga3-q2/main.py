import os
import base64
import io
import PIL.Image
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI()

# 1. Enable CORS to accept requests from any origin (Required for the grader)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Configure Gemini API
# You must set the GOOGLE_API_KEY environment variable in your deployment platform
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY environment variable not set!")
    
genai.configure(api_key=GOOGLE_API_KEY)
# gemini-1.5-flash is free, fast, and excellent for OCR/charts
model = genai.GenerativeModel("gemini-1.5-flash")

class QARequest(BaseModel):
    image_base64: str
    question: str

class QAResponse(BaseModel):
    answer: str

@app.post("/answer-image", response_model=QAResponse)
async def answer_image(request: QARequest):
    try:
        # 3. Decode Base64 Image
        img_str = request.image_base64
        # Remove metadata prefix if present (e.g., "data:image/png;base64,")
        if "," in img_str:
            img_str = img_str.split(",", 1)[1]
            
        image_data = base64.b64decode(img_str)
        image = PIL.Image.open(io.BytesIO(image_data))
        
        # 4. Prompt Engineering (Strict rules for numeric answers)
        prompt = f"""
        {request.question}
        
        CRITICAL FORMATTING RULES:
        - If the answer is a number, return ONLY the raw number (e.g., "4089.35").
        - DO NOT include currency symbols ($, ₹, €), commas, or units (%, kg, USD).
        - DO NOT include any explanations, conversational text, or markdown formatting.
        - Just output the exact answer.
        """
        
        # Generate response
        response = model.generate_content([prompt, image])
        answer = response.text.strip()
        
        # Clean up common LLM quirks (like wrapping the answer in quotes)
        answer = answer.strip('\'"')
        
        return {"answer": answer}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))