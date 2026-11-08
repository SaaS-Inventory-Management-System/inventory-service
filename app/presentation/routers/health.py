from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def health_check():
    return {"status": "ok"}

@router.get("/live")
def liveness_check():
    return {"status": "alive"}

@router.get("/ready")
def readiness_check():
    return {"status": "ready"}