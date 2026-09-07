from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("")
@router.get("/{path:path}")
@router.post("")
@router.post("/{path:path}")
@router.put("/{path:path}")
@router.delete("/{path:path}")
async def calls_stub(path: str = ""):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Calls API endpoints are not implemented yet.",
    )
