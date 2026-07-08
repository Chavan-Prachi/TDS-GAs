from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# CORS for the CORS question
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

analytics_store = []
metrics_store = []

# POST Analytics Endpoint
@app.post("/analytics")
def post_analytics(data: dict):
    analytics_store.append(data)
    return {"status": "ok", "count": len(analytics_store)}

@app.get("/analytics")
def get_analytics():
    return {"data": analytics_store, "count": len(analytics_store)}

# Metrics API
@app.post("/metrics")
def post_metrics(data: dict):
    metrics_store.append(data)
    return {"status": "ok", "count": len(metrics_store)}

@app.get("/metrics")
def get_metrics():
    return {"data": metrics_store, "count": len(metrics_store)}

# 12-Factor Config Precedence
@app.get("/config")
def get_config():
    return {
        "APP_ENV": os.getenv("APP_ENV", "development"),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "info"),
        "DB_URL": os.getenv("DB_URL", "sqlite:///local.db")
    }

# Keep your Q2 verify endpoint if you still have it, or just leave it out if Q2 is saved.