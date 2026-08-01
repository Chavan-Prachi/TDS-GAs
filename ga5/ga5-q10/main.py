import hashlib
import json
import os
import uuid
import sqlite3
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
client = OpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "dummy-key")
)
DB_PATH = "a2a_agent.db"
PACKAGE_CACHE = {}  # In-memory cache for canonical package decisions

# --- FastAPI Setup ---
app = FastAPI(title="A2A Invoice Agent")

class A2AJSONResponse(JSONResponse):
    media_type = "application/a2a+json"

# --- Database Setup ---
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            principal_id TEXT,
            message_id TEXT,
            message_hash TEXT,
            state TEXT,
            task_json TEXT,
            UNIQUE(principal_id, message_hash)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_principal_message_id ON tasks(principal_id, message_id)")
    conn.commit()
    conn.close()

init_db()

# --- Helpers ---
def verify_auth(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return authorization.split(" ")[1]

def verify_a2a_headers(
    a2a_version: Optional[str] = Header(None, alias="A2A-Version"),
    content_type: Optional[str] = Header(None)
):
    if a2a_version != "1.0":
        raise HTTPException(status_code=400, detail="Invalid A2A-Version. Must be 1.0")
    if content_type and "application/a2a+json" not in content_type:
        raise HTTPException(status_code=400, detail="Invalid Content-Type. Must be application/a2a+json")

def compute_message_hash(message: dict) -> str:
    return hashlib.sha256(json.dumps(message, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

# --- AI Processing ---
def process_invoice_batch(packages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    proposals = []
    packages_to_process = []
    
    for pkg in packages:
        pkg_hash = hashlib.sha256(json.dumps(pkg, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        if pkg_hash in PACKAGE_CACHE:
            proposals.append(PACKAGE_CACHE[pkg_hash])
        else:
            packages_to_process.append(pkg)
            
    if packages_to_process:
        prompt = f"""You are an invoice processing agent. Analyze the following invoice packages and choose exactly ONE action for each:
- settle_invoice: valid, reconciled, and within autonomous authority.
- request_approval: commercially valid, but outside delegated authority.
- hold_invoice: payment pauses until a stated verification completes.
- reject_duplicate: the same commercial invoice was already paid.
- open_exception: material records conflict and need an exception workflow.

Return a JSON object with a single key "proposals" containing an array of objects. Each object MUST have:
- packageId: string (must exactly match the input packageId)
- actionId: string (durable unique id, at least 12 characters, e.g., 'act_' + uuid)
- action: string (one of the 5 actions above, exactly as written)
- facts: object with vendorName (string), invoiceNumber (string), amountMinor (int), currency (string, e.g., "INR")
- evidenceRefs: array of EXACTLY THREE decisive bracketed references from the documents (e.g., ["[1]", "[2]", "[3]"). Do NOT include cover-sheet references, archive examples, or training decoys.
- rationale: string (60-1500 characters; name the action and cite at least two evidence refs).

Packages:
{json.dumps(packages_to_process, indent=2)}

Return ONLY a valid JSON object with the "proposals" key. Do not include markdown formatting or any other text. Carefully ignore old examples, negation, and irrelevant action words.
"""
        response = client.chat.completions.create(
            model=os.getenv("AI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        try:
            if content.strip().startswith("```json"):
                content = content.strip()[7:-3].strip()
            elif content.strip().startswith("```"):
                content = content.strip()[3:-3].strip()
            
            parsed = json.loads(content)
            new_proposals = parsed.get("proposals", [])
            
            for prop in new_proposals:
                pkg_hash = hashlib.sha256(json.dumps(next(p for p in packages_to_process if p["packageId"] == prop["packageId"]), sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
                PACKAGE_CACHE[pkg_hash] = prop
                proposals.append(prop)
                
        except Exception as e:
            print(f"AI parsing error: {e}, content: {content}")
            raise HTTPException(status_code=500, detail="AI processing failed")
            
    return proposals

# --- Pydantic Models ---
class MessagePart(BaseModel):
    mediaType: str
    data: Any

class Message(BaseModel):
    messageId: str
    taskId: Optional[str] = None
    contextId: Optional[str] = None
    role: str
    parts: List[MessagePart]

class Configuration(BaseModel):
    returnImmediately: bool = False
    historyLength: int = 20
    acceptedOutputModes: List[str]

class SendMessageRequest(BaseModel):
    message: Message
    configuration: Optional[Configuration] = None

# --- Endpoints ---
@app.get("/.well-known/agent-card.json", response_class=A2AJSONResponse)
def get_agent_card():
    return {
        "name": "A2A Invoice Agent",
        "description": "An AI agent that processes invoice batches and proposes actions.",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "skills": [{
            "name": "invoice_action_agent",
            "description": "Processes invoice claim batches and proposes actions like settle, approve, hold, reject, or exception.",
            "tags": ["invoice", "finance", "a2a"]
        }],
        "supportedInterfaces": [{
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": "1.0",
            "url": os.getenv("BASE_URL", "https://delegate.example/a2a/")
        }],
        "defaultInputModes": ["application/vnd.ga5.invoice-claim-batch+json"],
        "defaultOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json"
        ]
    }

@app.post("/message:send", response_class=A2AJSONResponse)
def send_message(
    req: SendMessageRequest, 
    principal_id: str = Depends(verify_auth), 
    a2a_version: str = Depends(verify_a2a_headers)
):
    message_dict = req.message.model_dump()
    msg_hash = compute_message_hash(message_dict)
    message_id = req.message.messageId
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Idempotent retry check
    cursor.execute("SELECT state, task_json FROM tasks WHERE principal_id = ? AND message_hash = ?", (principal_id, msg_hash))
    row = cursor.fetchone()
    if row:
        conn.close()
        return {"task": json.loads(row["task_json"])}
    
    # 2. Message ID conflict check
    cursor.execute("SELECT message_hash FROM tasks WHERE principal_id = ? AND message_id = ?", (principal_id, message_id))
    conflict_row = cursor.fetchone()
    if conflict_row and conflict_row["message_hash"] != msg_hash:
        conn.close()
        raise HTTPException(status_code=409, detail={"error": "IDEMPOTENCY_CONFLICT", "message": "Message ID reused with different content"})
    
    # 3. Continuation vs New Task
    task_id = req.message.taskId or f"task_{uuid.uuid4().hex}"
    context_id = req.message.contextId or f"ctx_{uuid.uuid4().hex}"
    
    if req.message.taskId and req.message.contextId:
        cursor.execute("SELECT state, task_json FROM tasks WHERE task_id = ? AND principal_id = ?", (task_id, principal_id))
        task_row = cursor.fetchone()
        if not task_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Task not found")
        
        task = json.loads(task_row["task_json"])
        if task.get("contextId") != context_id:
            conn.close()
            raise HTTPException(status_code=400, detail="Context ID mismatch")
        
        result_part = req.message.parts[0] if req.message.parts else None
        if result_part and result_part.mediaType == "application/vnd.ga5.invoice-action-results+json":
            results_data = result_part.data
            batch_id = results_data.get("batchId")
            
            proposal_msg = next((m for m in task["history"] if m.get("role") == "ROLE_MODEL"), None)
            if not proposal_msg:
                conn.close()
                raise HTTPException(status_code=400, detail="No proposal found in history")
            
            proposals = proposal_msg["parts"][0]["data"]["proposals"]
            proposals_dict = {p["packageId"]: p for p in proposals}
            
            executions = []
            for res in results_data.get("results", []):
                if res["outcome"] == "ACCEPTED":
                    prop = proposals_dict.get(res["packageId"])
                    if not prop or prop["actionId"] != res["actionId"] or prop["action"] != res["action"]:
                        conn.close()
                        raise HTTPException(status_code=400, detail="Proposal mismatch")
                    
                    executions.append({
                        "packageId": res["packageId"],
                        "actionId": res["actionId"],
                        "action": res["action"],
                        "receiptNonce": res["receiptNonce"],
                        "facts": prop["facts"],
                        "evidenceRefs": prop["evidenceRefs"]
                    })
            
            receipt_part = {
                "mediaType": "application/vnd.ga5.invoice-action-receipts+json",
                "data": {"batchId": batch_id, "executions": executions}
            }
            
            task["history"].append({
                "messageId": message_id, "taskId": task_id, "contextId": context_id,
                "role": "ROLE_USER", "parts": [result_part.model_dump()]
            })
            task["history"].append({
                "messageId": f"model_{uuid.uuid4().hex}", "taskId": task_id, "contextId": context_id,
                "role": "ROLE_MODEL", "parts": [receipt_part]
            })
            task["state"] = "TASK_STATE_COMPLETED"
            
            cursor.execute("BEGIN IMMEDIATE")
            try:
                cursor.execute("SELECT state FROM tasks WHERE task_id = ? AND principal_id = ?", (task_id, principal_id))
                latest_state = cursor.fetchone()["state"]
                if latest_state in ["TASK_STATE_COMPLETED", "TASK_STATE_CANCELED"]:
                    conn.rollback()
                    conn.close()
                    raise HTTPException(status_code=409, detail="Task already terminal")
                
                cursor.execute(
                    "UPDATE tasks SET state = ?, task_json = ?, message_id = ?, message_hash = ? WHERE task_id = ? AND principal_id = ?", 
                    (task["state"], json.dumps(task), message_id, msg_hash, task_id, principal_id)
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
            return {"task": task}
        
        # Fallback for non-result continuations
        task["history"].append({
            "messageId": message_id, "taskId": task_id, "contextId": context_id,
            "role": "ROLE_USER", "parts": [p.model_dump() for p in req.message.parts]
        })
        cursor.execute("UPDATE tasks SET task_json = ?, message_id = ?, message_hash = ? WHERE task_id = ? AND principal_id = ?", 
                       (json.dumps(task), message_id, msg_hash, task_id, principal_id))
        conn.commit()
        conn.close()
        return {"task": task}

    # 4. Initial Message Processing (AI Call)
    batch_part = next((p for p in req.message.parts if p.mediaType == "application/vnd.ga5.invoice-claim-batch+json"), None)
    if not batch_part:
        conn.close()
        raise HTTPException(status_code=400, detail="Missing invoice claim batch")
    
    batch_data = batch_part.data
    proposals = process_invoice_batch(batch_data.get("packages", []))
    
    task = {
        "id": task_id,
        "contextId": context_id,
        "state": "TASK_STATE_INPUT_REQUIRED",
        "history": [
            {
                "messageId": message_id,
                "role": "ROLE_USER",
                "parts": [p.model_dump() for p in req.message.parts]
            },
            {
                "messageId": f"model_{uuid.uuid4().hex}",
                "role": "ROLE_MODEL",
                "parts": [{
                    "mediaType": "application/vnd.ga5.invoice-action-proposals+json",
                    "data": {"batchId": batch_data.get("batchId"), "proposals": proposals}
                }]
            }
        ]
    }
    
    cursor.execute(
        "INSERT INTO tasks (task_id, principal_id, message_id, message_hash, state, task_json) VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, principal_id, message_id, msg_hash, task["state"], json.dumps(task))
    )
    conn.commit()
    conn.close()
    
    return {"task": task}

@app.get("/tasks", response_class=A2AJSONResponse)
def list_tasks(principal_id: str = Depends(verify_auth), a2a_version: str = Depends(verify_a2a_headers)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT task_json FROM tasks WHERE principal_id = ?", (principal_id,))
    rows = cursor.fetchall()
    conn.close()
    return {"tasks": [json.loads(row["task_json"]) for row in rows]}

@app.get("/tasks/{task_id}", response_class=A2AJSONResponse)
def get_task(task_id: str, principal_id: str = Depends(verify_auth), a2a_version: str = Depends(verify_a2a_headers)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT task_json FROM tasks WHERE task_id = ? AND principal_id = ?", (task_id, principal_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": json.loads(row["task_json"])}

@app.post("/tasks/{task_id}:cancel", response_class=A2AJSONResponse)
def cancel_task(task_id: str, principal_id: str = Depends(verify_auth), a2a_version: str = Depends(verify_a2a_headers)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    try:
        cursor.execute("SELECT state, task_json FROM tasks WHERE task_id = ? AND principal_id = ?", (task_id, principal_id))
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            conn.close()
            raise HTTPException(status_code=404, detail="Task not found")
        
        task = json.loads(row["task_json"])
        if task["state"] in ["TASK_STATE_COMPLETED", "TASK_STATE_CANCELED", "TASK_STATE_FAILED"]:
            conn.rollback()
            conn.close()
            raise HTTPException(status_code=409, detail="Task already terminal")
        
        task["state"] = "TASK_STATE_CANCELED"
        cursor.execute(
            "UPDATE tasks SET state = ?, task_json = ? WHERE task_id = ? AND principal_id = ?", 
            (task["state"], json.dumps(task), task_id, principal_id)
        )
        conn.commit()
        conn.close()
        return {"task": task}
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e