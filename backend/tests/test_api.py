"""
Integration-style tests for the FastAPI app.

These do NOT call the real Gemini API — network access is mocked so tests
run fast, free, and deterministically in CI.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_generate_plan_rejects_invalid_payload():
    # Missing required fields entirely
    response = client.post("/api/generate-plan", json={"user": {}})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"


def test_generate_plan_rejects_out_of_range_age():
    payload = {
        "user": {
            "full_name": "Test User",
            "age": 5,  # below allowed minimum of 13
            "gender": "female",
            "height_cm": 165,
            "weight_kg": 60,
            "fitness_goal": "maintain",
            "fitness_level": "beginner",
            "workout_location": "home",
            "equipment": ["none"],
            "workout_duration": 30,
            "workout_days": 3,
            "diet_preference": "no-preference",
        }
    }
    response = client.post("/api/generate-plan", json=payload)
    assert response.status_code == 422


def test_chat_rejects_empty_message():
    payload = {
        "user": {
            "full_name": "Test User",
            "age": 25,
            "gender": "male",
            "height_cm": 175,
            "weight_kg": 75,
            "fitness_goal": "maintain",
            "fitness_level": "intermediate",
            "workout_location": "gym",
            "equipment": ["full-gym"],
            "workout_duration": 45,
            "workout_days": 5,
            "diet_preference": "no-preference",
        },
        "message": "",
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
