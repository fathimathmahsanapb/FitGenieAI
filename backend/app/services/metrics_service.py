"""
Deterministic health metric calculations.

Pure functions only — no I/O, no AI calls — so they are trivially unit
testable and cheap to run on every request. Mirrors the reference logic
documented in the FitGenie AI architecture blueprint (Mifflin-St Jeor for
BMR, activity-adjusted TDEE, etc.).
"""

import random

from app.models.plan_schema import BMIInfo, MetricsPayload
from app.models.user_schema import FitnessGoal, FitnessLevel, Gender, UserProfile

# Activity multipliers used to derive TDEE from BMR, keyed by fitness level.
# (A simplified proxy for the standard Harris-Benedict/Mifflin activity
# scale, consistent with the multipliers used in the frontend mock.)
_ACTIVITY_MULTIPLIER = {
    FitnessLevel.beginner: 1.375,
    FitnessLevel.intermediate: 1.55,
    FitnessLevel.advanced: 1.725,
}

# Calorie adjustment applied to TDEE based on stated goal.
_GOAL_ADJUSTMENT = {
    FitnessGoal.lose_weight: -450,
    FitnessGoal.gain_muscle: +350,
    FitnessGoal.maintain: 0,
    FitnessGoal.improve_endurance: 0,
}

_MOTIVATIONS = [
    "Discipline is choosing between what you want now and what you want most.",
    "Small consistent steps beat occasional giant leaps. Show up today.",
    "Your body can stand almost anything. It's your mind you have to convince.",
    "Progress, not perfection \u2014 every rep counts.",
    "The only bad workout is the one that didn't happen.",
    "Fuel your body like you actually love it, because you do.",
]


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return round(weight_kg / (height_m**2), 1)


def classify_bmi(bmi: float) -> str:
    if bmi < 18.5:
        return "Underweight"
    if bmi < 25:
        return "Normal"
    if bmi < 30:
        return "Overweight"
    return "Obese"


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: Gender) -> float:
    """Mifflin-St Jeor equation."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == Gender.male:
        return base + 5
    if gender == Gender.female:
        return base - 161
    # "other" — use the midpoint between the male/female offsets
    return base - 78


def calculate_tdee(bmr: float, fitness_level: FitnessLevel) -> float:
    return bmr * _ACTIVITY_MULTIPLIER.get(fitness_level, 1.4)


def calculate_calorie_target(tdee: float, goal: FitnessGoal) -> int:
    return round(tdee + _GOAL_ADJUSTMENT.get(goal, 0))


def calculate_water_intake_ml(weight_kg: float, fitness_level: FitnessLevel) -> int:
    base = weight_kg * 33  # ml per kg baseline
    bonus = {
        FitnessLevel.beginner: 0,
        FitnessLevel.intermediate: 300,
        FitnessLevel.advanced: 500,
    }.get(fitness_level, 0)
    return round(base + bonus)


def calculate_macros(calorie_target: int) -> dict:
    """Approximate 30/40/30 protein/carb/fat split, in grams."""
    return {
        "protein": round((calorie_target * 0.30) / 4),
        "carbs": round((calorie_target * 0.40) / 4),
        "fat": round((calorie_target * 0.30) / 9),
    }


def random_motivation() -> str:
    return random.choice(_MOTIVATIONS)


def build_metrics_payload(user: UserProfile) -> MetricsPayload:
    """Compute the full deterministic metrics bundle for a user profile."""
    bmi = calculate_bmi(user.weight_kg, user.height_cm)
    bmr = calculate_bmr(user.weight_kg, user.height_cm, user.age, user.gender)
    tdee = calculate_tdee(bmr, user.fitness_level)
    calorie_target = calculate_calorie_target(tdee, user.fitness_goal)

    return MetricsPayload(
        bmi_info=BMIInfo(bmi=bmi, category=classify_bmi(bmi)),
        bmr=round(bmr),
        tdee=round(tdee),
        calorie_recommendation=calorie_target,
        macros=calculate_macros(calorie_target),
        water_intake_ml=calculate_water_intake_ml(user.weight_kg, user.fitness_level),
        motivation=random_motivation(),
    )
