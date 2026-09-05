"""Covenant Certificate's deliberately small, deterministic API."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.covenant import DEMO_CASES, RunRequest, case_summary, run_case

app = FastAPI(title="Covenant Certificate API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "covenant-certificate"}


@app.get("/api/demo-cases")
async def demo_cases() -> list[dict]:
    return [case_summary(case) for case in DEMO_CASES.values()]


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    case = DEMO_CASES.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown covenant case")
    return case_summary(case)


@app.post("/api/cases/{case_id}/run")
async def run(case_id: str, request: RunRequest = RunRequest()) -> dict:
    case = DEMO_CASES.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown covenant case")
    return run_case(case, request)
