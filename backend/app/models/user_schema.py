"""
Pydantic schemas describing the user's fitness profile.

These mirror the fields collected by the frontend Fitness Assessment form
exactly, so the request body maps 1:1 with what the UI submits.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"


class FitnessGoal(str, Enum):
    lose_weight = "lose-weight"
    gain_muscle = "gain-muscle"
    maintain = "maintain"
    improve_endurance = "improve-endurance"


class FitnessLevel(str, Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"


class WorkoutLocation(str, Enum):
    home = "home"
    gym = "gym"
    outdoor = "outdoor"


class Equipment(str, Enum):
    none = "none"
    dumbbells = "dumbbells"
    resistance_bands = "resistance-bands"
    barbell = "barbell"
    full_gym = "full-gym"


class DietPreference(str, Enum):
    no_preference = "no-preference"
    vegetarian = "vegetarian"
    vegan = "vegan"
    keto = "keto"
    paleo = "paleo"
    high_protein = "high-protein"


class UserProfile(BaseModel):
    """A single user's fitness assessment submission."""

    full_name: str = Field(..., min_length=2, max_length=80, examples=["Aisha Rahman"])
    age: int = Field(..., ge=13, le=90)
    gender: Gender
    height_cm: float = Field(..., ge=100, le=250)
    weight_kg: float = Field(..., ge=30, le=300)

    fitness_goal: FitnessGoal
    fitness_level: FitnessLevel

    workout_location: WorkoutLocation
    equipment: List[Equipment] = Field(default_factory=list)
    workout_duration: int = Field(..., ge=10, le=120, description="Minutes per session")
    workout_days: int = Field(..., ge=1, le=7)

    diet_preference: DietPreference
    allergies: Optional[str] = Field(default=None, max_length=200)
    medical_conditions: Optional[str] = Field(default=None, max_length=500)

    @field_validator("equipment")
    @classmethod
    def dedupe_equipment(cls, v: List[Equipment]) -> List[Equipment]:
        # If "none" is selected alongside other equipment, "none" wins —
        # it is the safest / most restrictive interpretation.
        if Equipment.none in v:
            return [Equipment.none]
        return list(dict.fromkeys(v))

    @field_validator("allergies", "medical_conditions")
    @classmethod
    def blank_to_none(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip() == "":
            return None
        return v

    @property
    def has_no_equipment(self) -> bool:
        return len(self.equipment) == 0 or self.equipment == [Equipment.none]

    @property
    def has_medical_conditions(self) -> bool:
        return bool(self.medical_conditions and self.medical_conditions.strip())

    model_config = {
        "json_schema_extra": {
            "example": {
                "full_name": "Aisha Rahman",
                "age": 28,
                "gender": "female",
                "height_cm": 165,
                "weight_kg": 68,
                "fitness_goal": "lose-weight",
                "fitness_level": "beginner",
                "workout_location": "home",
                "equipment": ["none"],
                "workout_duration": 30,
                "workout_days": 4,
                "diet_preference": "vegetarian",
                "allergies": "peanuts",
                "medical_conditions": "mild knee pain",
            }
        }
    }
