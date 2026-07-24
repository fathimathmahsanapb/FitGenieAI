"""
Prompt engineering layer for FitGenie AI.

Isolating prompt construction here means prompt tuning never touches
routing or business logic, and every rule required by the product spec
(equipment awareness, location awareness, duration awareness, fitness-level
awareness, medical awareness) is enforced in exactly one place.
"""

from typing import List

from app.models.chat_schema import ChatMessage
from app.models.plan_schema import MetricsPayload
from app.models.user_schema import Equipment, UserProfile

# ------------------------------------------------------------------
# Shared persona / safety system prompt
# ------------------------------------------------------------------
BASE_SYSTEM_PROMPT = """You are FitGenie, a certified-style AI fitness and nutrition assistant \
embedded in the FitGenie AI application. You provide safe, practical, evidence-informed \
fitness and nutrition guidance.

Hard rules you must always follow:
- You are NOT a doctor. Never diagnose medical conditions. For any medical concern, \
recommend the user consult a licensed healthcare professional.
- Never recommend extreme or unsafe practices (e.g. calorie intake below 1200 kcal/day, \
excessive training volume, ignoring pain/injury).
- Only recommend exercises and equipment that match the user's stated location and \
available equipment. Never suggest equipment the user does not have access to.
- Keep all workouts realistically achievable within the user's selected session duration.
- Adjust exercise intensity, volume, and complexity to the user's fitness level.
- If the user has disclosed medical conditions, explicitly account for them and include a \
short safety note (e.g. modifications or a caution to consult a professional).
- Be encouraging, concise, and specific. Avoid filler and disclaimers-as-padding \u2014 one \
clear safety note is enough, not one per paragraph."""


# Equipment/machine terms that must never appear in a "No Equipment" plan.
# Kept as base/singular forms since substring matching also catches plurals
# (e.g. "dumbbell" matches "dumbbells").
FORBIDDEN_EQUIPMENT_TERMS = [
    "dumbbell",
    "barbell",
    "kettlebell",
    "resistance band",
    "resistance-band",
    "jump rope",
    "jump-rope",
    "skipping rope",
    "pull-up bar",
    "pull up bar",
    "pullup bar",
    "rowing machine",
    "rower",
    "treadmill",
    "elliptical",
    "cable machine",
    "cable crossover",
    "smith machine",
    "leg press",
    "gym machine",
    "weight machine",
    "lat pulldown",
]


def equipment_violation_terms(plan_text: str) -> List[str]:
    """
    Scan generated plan text for forbidden equipment-based terms.

    Used by plan_router as a server-side safety net after generation, since
    an LLM is never 100% guaranteed to follow prompt instructions. Returns
    the forbidden terms found (deduplicated, in first-encountered order).
    """
    lowered = plan_text.lower()
    return [term for term in FORBIDDEN_EQUIPMENT_TERMS if term in lowered]


def _equipment_instruction(user: UserProfile) -> str:
    if user.has_no_equipment:
        forbidden_list = "\n".join(f"- {term.title()}" for term in [
            "Dumbbells", "Barbells", "Kettlebells", "Resistance Bands",
            "Jump Rope", "Pull-up Bar", "Rowing Machine", "Treadmill",
            "Elliptical", "Cable Machine", "Smith Machine", "Leg Press",
            "Any Gym Machine",
        ])
        return (
            "EQUIPMENT CONSTRAINT \u2014 STRICT REQUIREMENT, NOT A SUGGESTION:\n"
            "The user selected NO EQUIPMENT. Every single exercise in this plan MUST be "
            "a bodyweight-only movement requiring zero equipment (e.g. push-ups, squats, "
            "lunges, planks, burpees, mountain climbers, glute bridges, sit-ups, high "
            "knees, jumping jacks).\n\n"
            "You are STRICTLY FORBIDDEN from mentioning, suggesting, or referencing any "
            "of the following, under any circumstances, for any reason:\n"
            f"{forbidden_list}\n\n"
            "If your response includes ANY forbidden item above, or any other equipment "
            "or machine of any kind, the response is INCORRECT. Re-check every exercise "
            "you list against this forbidden list before finalizing your answer."
        )
    equipment_list = ", ".join(e.value.replace("-", " ") for e in user.equipment)
    return (
        f"EQUIPMENT CONSTRAINT: The user has access to ONLY the following equipment: "
        f"{equipment_list}. Do not recommend exercises requiring equipment outside this list."
    )


def _location_instruction(user: UserProfile) -> str:
    mapping = {
        "home": (
            "LOCATION CONSTRAINT: Workouts take place at HOME. Avoid gym-only machines "
            "(e.g. lat pulldown machine, leg press, cable stations, Smith machine). "
            "Favor exercises that work in a small space."
        ),
        "gym": (
            "LOCATION CONTEXT: Workouts take place at a fully equipped GYM. Free weights, "
            "machines, and cardio equipment may be used if they match the user's equipment list."
        ),
        "outdoor": (
            "LOCATION CONSTRAINT: Workouts take place OUTDOORS. Favor running, sprints, "
            "bodyweight circuits, and exercises usable with minimal or portable equipment. "
            "Avoid machine-based exercises."
        ),
    }
    return mapping.get(user.workout_location.value, "")


def _duration_instruction(user: UserProfile) -> str:
    return (
        f"DURATION CONSTRAINT: Each workout session must fit within "
        f"{user.workout_duration} minutes total, including a brief warm-up and cool-down. "
        f"Size the number of exercises and sets/reps accordingly \u2014 do not overload the session."
    )


def _level_instruction(user: UserProfile) -> str:
    mapping = {
        "beginner": (
            "FITNESS LEVEL: BEGINNER. Prioritize proper form, lower volume (2-3 sets), "
            "simpler movement patterns, and longer rest periods (60-90s). Include form cues."
        ),
        "intermediate": (
            "FITNESS LEVEL: INTERMEDIATE. Moderate volume (3-4 sets), moderate rest "
            "(45-75s), can include some compound and tempo variations."
        ),
        "advanced": (
            "FITNESS LEVEL: ADVANCED. Higher volume/intensity (4-5 sets), shorter rest "
            "(30-60s), may include advanced variations, supersets, or progressive overload cues."
        ),
    }
    return mapping.get(user.fitness_level.value, "")


def _medical_instruction(user: UserProfile) -> str:
    if not user.has_medical_conditions:
        return "MEDICAL CONTEXT: The user reported no medical conditions."
    return (
        f"MEDICAL CONTEXT: The user disclosed the following condition(s): "
        f"\"{user.medical_conditions}\". You MUST take this into account \u2014 avoid or modify "
        f"any exercise that could aggravate this condition, and include one short, clear "
        f"safety note recommending the user confirm the plan with a healthcare professional "
        f"before starting, especially for high-impact or high-risk movements."
    )


def _diet_instruction(user: UserProfile) -> str:
    allergy_note = (
        f" The user is allergic to: {user.allergies}. NEVER include this in any meal "
        f"or ingredient."
        if user.allergies
        else " The user reported no food allergies."
    )
    return (
        f"DIET CONSTRAINT: Diet preference is '{user.diet_preference.value.replace('-', ' ')}'."
        f"{allergy_note}"
    )


def build_plan_prompt(
    user: UserProfile,
    metrics: MetricsPayload,
    strict_retry: bool = False,
    previous_violations: List[str] | None = None,
) -> str:
    """
    Build the full user-turn prompt for POST /api/generate-plan.
    The AI is asked to return the workout plan and meal plan together in a
    consistent, markdown-friendly structure the frontend can render
    progressively while it streams.

    If `strict_retry` is True, an additional regeneration notice is appended
    (used by plan_router when a first attempt violated the equipment
    constraint), naming the specific forbidden terms that were found so the
    model can't repeat the same mistake.
    """
    constraints = "\n".join(
        [
            _equipment_instruction(user),
            _location_instruction(user),
            _duration_instruction(user),
            _level_instruction(user),
            _medical_instruction(user),
            _diet_instruction(user),
        ]
    )

    profile_block = f"""User Profile:
- Name: {user.full_name}
- Age: {user.age}, Gender: {user.gender.value}
- Height: {user.height_cm} cm, Weight: {user.weight_kg} kg
- BMI: {metrics.bmi_info.bmi} ({metrics.bmi_info.category})
- Goal: {user.fitness_goal.value.replace('-', ' ')}
- Daily calorie target: {metrics.calorie_recommendation} kcal \
(protein {metrics.macros['protein']}g / carbs {metrics.macros['carbs']}g / fat {metrics.macros['fat']}g)
- Workout days per week: {user.workout_days}"""

    output_format = f"""Respond in this exact Markdown structure, and nothing else. Keep every \
line concise (one short line per item) so the full response fits within the available length \
\u2014 do not stop early and do not omit any section:

## Workout Plan
### Day 1: <Focus Area>
- Warm-up: <1 short line>
- <Exercise> \u2014 <sets> x <reps or duration>
- <Exercise> \u2014 <sets> x <reps or duration>
- <Exercise> \u2014 <sets> x <reps or duration>
- Cool-down: <1 short line>

(Repeat for all {user.workout_days} workout days, each as its own "### Day N: <Focus Area>" \
block, fitting the {user.workout_duration}-minute duration constraint.)

## Meal Plan
### Breakfast
<one short meal suggestion aligned to diet preference and allergies>
### Lunch
<one short meal suggestion>
### Dinner
<one short meal suggestion>
### Snack
<one short meal suggestion>

## Safety Note
<one short sentence, only if medically relevant; otherwise a brief general safety reminder>

MANDATORY COMPLETENESS CHECK: Your response is INCOMPLETE and INCORRECT unless it contains ALL \
{user.workout_days} day blocks (Day 1 through Day {user.workout_days}), the full Meal Plan \
section with all 4 meals, and the Safety Note. Do not truncate or stop partway through \u2014 \
keep descriptions brief specifically so you have enough room to finish every section.
"""

    prompt = f"{profile_block}\n\nConstraints:\n{constraints}\n\n{output_format}"

    if strict_retry:
        violation_list = ", ".join(previous_violations) if previous_violations else "equipment-based exercises"
        prompt += (
            "\n\nREGENERATION NOTICE: Your previous attempt at this plan incorrectly "
            f"included forbidden equipment-based content ({violation_list}). That "
            "response was rejected. Generate the ENTIRE plan again from scratch using "
            "ONLY bodyweight exercises with zero equipment. Carefully verify every "
            "exercise before responding \u2014 including any forbidden equipment or "
            "equipment-based exercise will make this response incorrect again."
        )

    return prompt


def build_chat_messages(
    user: UserProfile,
    workout_plan: str | None,
    meal_plan: str | None,
    message: str,
    history: List[ChatMessage],
) -> List[dict]:
    """
    Build the full chat `messages` array for POST /api/chat, injecting a
    condensed profile + plan summary once (not repeated every turn) plus a
    rolling window of recent conversation history.
    """
    context_lines = [
        f"You are chatting with {user.full_name}, age {user.age}, gender {user.gender.value}.",
        f"Fitness goal: {user.fitness_goal.value.replace('-', ' ')}; "
        f"level: {user.fitness_level.value}; "
        f"location: {user.workout_location.value}; "
        f"diet preference: {user.diet_preference.value.replace('-', ' ')}.",
    ]
    if user.allergies:
        context_lines.append(f"Food allergies: {user.allergies}. Never recommend these.")
    if user.has_medical_conditions:
        context_lines.append(
            f"Medical conditions disclosed: {user.medical_conditions}. Be cautious and "
            f"recommend professional consultation where relevant."
        )
    if workout_plan:
        context_lines.append(f"Their current AI-generated workout plan:\n{workout_plan[:2500]}")
    if meal_plan:
        context_lines.append(f"Their current AI-generated meal plan:\n{meal_plan[:1500]}")
    if workout_plan or meal_plan:
        context_lines.append(
            "GROUNDING RULE: When the user asks about their plan \u2014 including whether "
            "it requires equipment, which exercises/meals it includes, how many days it "
            "covers, or its structure \u2014 answer directly and specifically using the "
            "plan text above. Name the actual exercises or meals involved. Do NOT give "
            "generic fitness advice when the answer can be derived from the plan text "
            "itself. For example, if asked whether the plan requires equipment, check "
            "the plan text for equipment-based exercises and answer 'Yes' (naming them) "
            "or 'No' (bodyweight only) accordingly."
        )

    system_prompt = BASE_SYSTEM_PROMPT + "\n\n" + "\n".join(context_lines)

    messages: List[dict] = [{"role": "system", "content": system_prompt}]

    # Rolling window: keep only the last 10 turns to control token cost.
    for turn in history[-10:]:
        messages.append({"role": turn.role.value, "content": turn.content})

    messages.append({"role": "user", "content": message})
    return messages
