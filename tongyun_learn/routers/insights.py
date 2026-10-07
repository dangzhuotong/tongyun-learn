"""P3b 读接口：/weak、/recall、/summary/week，以及人工改状态 PATCH /points/{id}/state。"""

from fastapi import APIRouter

router = APIRouter(tags=["insights"])
