import os
import base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

# 1. Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Configure Groq Client
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable not set!")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

class QARequest(BaseModel):
    image_base64: str
    question: str

class QAResponse(BaseModel):
    answer: str

@app.post("/answer-image", response_model=QAResponse)
async def answer_image(request: QARequest):
    try:
        img_str = request.image_base64
        if "," in img_str:
            img_str = img_str.split(",", 1)[1]
            
        # 3. Strict Prompt
        prompt = f"""
        {request.question}
        
        CRITICAL FORMATTING RULES:
        - If the answer is a number, return ONLY the raw number (e.g., "4089.35").
        - DO NOT include currency symbols ($, ₹, €), commas, or units (%, kg, USD).
        - DO NOT include any explanations, conversational text, or markdown formatting.
        - Just output the exact answer.
        """
        
        # 4. Call Groq's Llama 3.2 Vision Model
        completion = client.chat.completions.create(
            model="llama-3.2-90b-vision-preview", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
                        },
                    ],
                }
            ],
            temperature=0.1,
            max_tokens=50,
        )
        
        answer = completion.choices[0].message.content.strip().strip('\'"')
        return {"answer": answer}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))