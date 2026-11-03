"""Route composition for version 1 public endpoints."""

from fastapi import APIRouter

from app.api.v1 import auth, federation, hospitals, model, mri, trust

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(hospitals.router)
router.include_router(model.router)
router.include_router(mri.router)
router.include_router(federation.router)

router.include_router(trust.router)
