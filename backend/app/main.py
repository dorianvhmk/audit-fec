from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import upload, analyze, results

app = FastAPI(title="Audit Reconciliation API", version="1.0.0")

# Parse CORS_ORIGIN: supports "*" (wildcard) or comma-separated list of origins.
# Wildcard is the safe default for Railway/Vercel deployments; tighten in production
# by setting CORS_ORIGIN=https://your-app.vercel.app,https://other-origin.com
_raw_origins = settings.cors_origin.strip()
_cors_origins: list[str] = (
    ["*"] if _raw_origins == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)
# 'allow_credentials' is incompatible with wildcard per the CORS spec
_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(analyze.router)
app.include_router(results.router)


@app.get("/health")
def health():
    return {"status": "ok"}
