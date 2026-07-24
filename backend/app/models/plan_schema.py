"""
Schemas for the /api/generate-plan endpoint.

The endpoint streams its response (see routers/plan_router.py), but these
models define the shape of the request body and the structured "metrics"
payload that is sent as the first chunk of the stream, before the AI-written
plan text begins streaming in.
"""

from typing import Dict

from pydantic import BaseModel, Field

from app.models.user_schema import UserProfile


class GeneratePlanRequest(BaseModel):
    """Request body for POST /api/generate-plan."""

    user: UserProfile


class BMIInfo(BaseModel):
    bmi: float
    category: str


class MetricsPayload(BaseModel):
    """
    Deterministic (non-AI) metrics computed instantly from the profile.
    Sent as the first SSE event so the frontend can render BMI/calories/
    water cards immediately, without waiting for the AI plan to finish
    streaming.
    """

    bmi_info: BMIInfo
    bmr: int
    tdee: int
    calorie_recommendation: int
    macros: Dict[str, int] = Field(
        description="Approximate daily macro targets in grams: protein, carbs, fat"
    )
    water_intake_ml: int
    motivation: str
