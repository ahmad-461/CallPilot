from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
@router.get("/{path:path}")
@router.post("")
@router.post("/{path:path}")
@router.put("/{path:path}")
@router.delete("/{path:path}")
async def appointments_stub(path: str = ""):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Appointments API endpoints are not implemented yet.",
    )
