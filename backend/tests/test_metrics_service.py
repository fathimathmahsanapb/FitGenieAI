"""Unit tests for app.services.metrics_service (pure functions, no AI calls)."""

from app.models.user_schema import FitnessGoal, FitnessLevel, Gender, UserProfile
from app.services import metrics_service


def make_user(**overrides) -> UserProfile:
    defaults = dict(
        full_name="Test User",
        age=28,
        gender=Gender.female,
        height_cm=165,
        weight_kg=68,
        fitness_goal=FitnessGoal.lose_weight,
        fitness_level=FitnessLevel.beginner,
        workout_location="home",
        equipment=["none"],
        workout_duration=30,
        workout_days=4,
        diet_preference="vegetarian",
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def test_calculate_bmi():
    bmi = metrics_service.calculate_bmi(weight_kg=70, height_cm=175)
    assert bmi == 22.9


def test_classify_bmi_categories():
    assert metrics_service.classify_bmi(17.0) == "Underweight"
    assert metrics_service.classify_bmi(22.0) == "Normal"
    assert metrics_service.classify_bmi(28.0) == "Overweight"
    assert metrics_service.classify_bmi(32.0) == "Obese"


def test_calculate_bmr_male_vs_female_offset():
    bmr_male = metrics_service.calculate_bmr(80, 180, 30, Gender.male)
    bmr_female = metrics_service.calculate_bmr(80, 180, 30, Gender.female)
    # Male offset (+5) minus female offset (-161) = 166 difference
    assert round(bmr_male - bmr_female) == 166


def test_calorie_target_reflects_goal_direction():
    tdee = 2200
    lose = metrics_service.calculate_calorie_target(tdee, FitnessGoal.lose_weight)
    gain = metrics_service.calculate_calorie_target(tdee, FitnessGoal.gain_muscle)
    maintain = metrics_service.calculate_calorie_target(tdee, FitnessGoal.maintain)
    assert lose < maintain < gain


def test_water_intake_scales_with_activity_level():
    beginner = metrics_service.calculate_water_intake_ml(70, FitnessLevel.beginner)
    advanced = metrics_service.calculate_water_intake_ml(70, FitnessLevel.advanced)
    assert advanced > beginner


def test_build_metrics_payload_end_to_end():
    user = make_user()
    payload = metrics_service.build_metrics_payload(user)
    assert payload.bmi_info.bmi > 0
    assert payload.calorie_recommendation > 0
    assert payload.water_intake_ml > 0
    assert set(payload.macros.keys()) == {"protein", "carbs", "fat"}
