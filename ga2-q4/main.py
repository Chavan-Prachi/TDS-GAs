from fastapi import FastAPI
import redis.asyncio as redis

app = FastAPI()
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

@app.get("/healthz")
async def healthz():
    try:
        await redis_client.ping()
        return {"status": "ok", "redis": "up"}
    except Exception:
        return {"status": "error", "redis": "down"}

@app.post("/hit/{key}")
async def hit(key: str):
    count = await redis_client.incr(key)
    return {"key": key, "count": count}

@app.get("/count/{key}")
async def count(key: str):
    val = await redis_client.get(key)
    return {"key": key, "count": int(val) if val else 0}