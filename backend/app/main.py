import os

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI(title="Precedent")


@app.get("/health")
def health():
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
    return {"status": "ok", "pgvector": row[0] if row else None}