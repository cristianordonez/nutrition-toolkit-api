from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/calculate/")
async def calculate_energy() -> dict[str, int]:
    """Calculate nutrition needs based on user metrics.

    :return: A dictionary containing the calculated energy needs.
    """
    return {"kcal": 1000}


@router.get("/calculate/tubefeed")
async def calculate_tubefeed() -> dict[str, int]:
    """Calculate tubefeed energy needs.

    :return: A dictionary containing the calculated tubefeed energy needs.
    """
    return {"kcal": 500}
