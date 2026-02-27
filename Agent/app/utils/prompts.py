"""
Prompt template builders for all Gemma LLM calls.
All prompt strings live here — no hardcoded prompts elsewhere in the codebase.
"""

from __future__ import annotations

import json
from typing import Any


# ── Decomposition ────────────────────────────────────────────────────────────


def build_decomposition_prompt(
    message: str,
    user_context: str,
    history: list[dict[str, str]],
    allergy_context: str,
) -> str:
    """
    Build the prompt for Gemma call #1: query decomposition.

    The SAFETY section is mandatory and always placed before the user query.
    Anaphylactic allergens must always appear in sql_filters.exclude_allergens.
    """
    history_text = ""
    if history:
        history_lines = []
        for turn in history[-6:]:   # last 3 turns
            role = turn.get("role", "user").capitalize()
            history_lines.append(f"{role}: {turn.get('content', '')}")
        history_text = "\n".join(history_lines) + "\n"

    return f"""You are Kairos, a restaurant recommendation AI for Bangalore.
Your job is to decompose the user's query into a structured search plan.

## USER CONTEXT
{user_context}

## SAFETY — USER ALLERGIES (NEVER SKIP)
{allergy_context}
Always populate sql_filters.exclude_allergens with any allergen listed
as 'anaphylactic' severity. This is not optional.

## CONVERSATION HISTORY
{history_text}
## CURRENT USER MESSAGE
{message}

## OUTPUT FORMAT
Output only valid JSON matching the schema below.
No markdown fences. No preamble. No explanation.

{{
  "intent": "find_restaurant" | "get_info" | "compare" | "clarify",
  "sql_filters": {{
    "price_tiers": ["$$", "$$$"],
    "cuisine_types": ["south indian"],
    "area": "Koramangala",
    "min_rating": 4.0,
    "exclude_allergens": []
  }},
  "vector_query": "quiet romantic vegan anniversary dinner",
  "ui_preference": "radar_comparison" | "map_view" | "restaurant_list" | "text",
  "needs_clarification": false,
  "clarification_question": null
}}"""


# ── Evaluation ───────────────────────────────────────────────────────────────


def build_evaluation_prompt(
    message: str,
    user_context: str,
    restaurants_json: str,
    allergy_context: str,
) -> str:
    """
    Build the prompt for Gemma call #2: scoring and ranking restaurants.

    Includes allergy context so Gemma factors dietary compliance into scores.
    Returns a JSON array with scores for each restaurant.
    """
    return f"""You are Kairos, a restaurant recommendation AI for Bangalore.
Score the following restaurants for the user's query.

## USER CONTEXT
{user_context}

## SAFETY — USER ALLERGIES
{allergy_context}

## USER QUERY
{message}

## RESTAURANTS TO SCORE
{restaurants_json}

## SCORING DIMENSIONS (0–10 each)
- romance: how romantic / intimate is the atmosphere
- noise_level: how quiet / peaceful (10 = very quiet)
- food_quality: quality and variety of food
- vegan_options: availability of vegan / plant-based dishes
- value_for_money: price vs quality ratio

## OUTPUT FORMAT
Output only a valid JSON array. No markdown fences. No preamble. No explanation.
Each element must have: id, romance, noise_level, food_quality, vegan_options, value_for_money.

Example:
[
  {{"id": 1, "romance": 8.5, "noise_level": 7.0, "food_quality": 8.0, "vegan_options": 6.0, "value_for_money": 7.5}},
  {{"id": 2, "romance": 6.0, "noise_level": 9.0, "food_quality": 9.0, "vegan_options": 8.5, "value_for_money": 8.0}}
]"""


# ── Profiler ─────────────────────────────────────────────────────────────────


def build_profiler_prompt(message: str, response_summary: str) -> str:
    """
    Build the prompt to extract preference signals from a chat turn.

    NEVER returns allergy fields — allergies are updated only via the
    PATCH /users/{uid}/allergies endpoint from the Backend.
    """
    return f"""You are extracting user preference signals from a dining conversation.

## USER MESSAGE
{message}

## AGENT RESPONSE SUMMARY
{response_summary}

## YOUR TASK
Extract new preference signals ONLY from:
- dietary: dietary preferences (e.g. "vegan", "vegetarian", "halal")
- vibes: atmosphere preferences (e.g. "quiet", "romantic", "outdoor")
- cuisine_affinity: cuisines the user seems to like
- cuisine_aversion: cuisines the user seems to dislike
- price_comfort: price tiers the user is comfortable with (e.g. ["$$", "$$$"])

## RULES
- NEVER return allergy fields — allergies are never inferred from chat
- Only include fields where you found clear evidence in the conversation
- Output {{}} if nothing new was learned

## OUTPUT FORMAT
Output only valid JSON. No markdown fences. No preamble. No explanation.

Example:
{{"dietary": ["vegan"], "vibes": ["quiet", "romantic"], "cuisine_affinity": ["south indian"]}}"""


# ── Context builders ─────────────────────────────────────────────────────────


def build_user_context(preferences: dict[str, Any]) -> str:
    """Format user preferences as a human-readable context string for prompts."""
    parts = []

    dietary = preferences.get("dietary", [])
    if dietary:
        parts.append(f"Dietary preferences: {', '.join(dietary)}")

    vibes = preferences.get("vibes", [])
    if vibes:
        parts.append(f"Atmosphere preferences: {', '.join(vibes)}")

    cuisine_affinity = preferences.get("cuisine_affinity", [])
    if cuisine_affinity:
        parts.append(f"Cuisine preferences: {', '.join(cuisine_affinity)}")

    cuisine_aversion = preferences.get("cuisine_aversion", [])
    if cuisine_aversion:
        parts.append(f"Cuisines to avoid: {', '.join(cuisine_aversion)}")

    price_comfort = preferences.get("price_comfort", [])
    if price_comfort:
        parts.append(f"Price comfort: {', '.join(price_comfort)}")

    location_bias = preferences.get("location_bias", {})
    if location_bias and location_bias.get("area"):
        area = location_bias["area"]
        radius = location_bias.get("radius_km", 5)
        parts.append(f"Preferred location: {area} (within {radius} km)")

    custom_notes = preferences.get("custom_notes", "")
    if custom_notes:
        parts.append(f"Notes: {custom_notes}")

    return "\n".join(parts) if parts else "No preferences set."


def build_allergy_context(allergies: dict[str, Any]) -> str:
    """
    Format allergy data as a safety-critical context string.
    This string is inserted into every Gemma prompt.
    """
    confirmed = allergies.get("confirmed", [])
    intolerances = allergies.get("intolerances", [])
    severity = allergies.get("severity", {})

    if not confirmed and not intolerances:
        return "No known allergies on file."

    parts = ["SAFETY-CRITICAL ALLERGY INFORMATION:"]

    if confirmed:
        allergen_details = []
        for allergen in confirmed:
            sev = severity.get(allergen, "severe")
            allergen_details.append(f"{allergen} ({sev})")
        parts.append(f"  Confirmed allergens: {', '.join(allergen_details)}")

    if intolerances:
        parts.append(f"  Intolerances: {', '.join(intolerances)}")

    anaphylactic = [a for a in confirmed if severity.get(a) == "anaphylactic"]
    if anaphylactic:
        parts.append(
            f"  ⚠️  ANAPHYLACTIC ALLERGENS (MUST be in exclude_allergens): "
            f"{', '.join(anaphylactic)}"
        )

    return "\n".join(parts)


# ── ReAct planner ─────────────────────────────────────────────────────────────


def build_planner_prompt(
    user_context: str,
    allergy_context: str,
    history: list[dict[str, str]],
    message: str,
    observations: list[str],
) -> str:
    """
    Build the prompt for the ReAct planner called at the start of each loop iteration.

    The SAFETY section is mandatory and always placed before the user query.
    The planner must choose one of four tools and provide tool_input JSON.

    observations accumulates results from all previous tool calls in the current
    turn so that the planner has full context when deciding the next action.
    """
    history_text = ""
    if history:
        history_lines = []
        for turn in history[-6:]:   # last 3 turns (user + assistant pairs)
            role = turn.get("role", "user").capitalize()
            history_lines.append(f"{role}: {turn.get('content', '')}")
        history_text = "\n".join(history_lines) + "\n"

    observations_text = ""
    if observations:
        numbered = "\n".join(
            f"  [{i + 1}] {obs}" for i, obs in enumerate(observations)
        )
        observations_text = f"\n## OBSERVATIONS FROM PREVIOUS STEPS THIS TURN\n{numbered}\n"

    return f"""You are Kairos, a restaurant recommendation AI for Bangalore.
You are operating inside a ReAct (Reasoning + Acting) loop.
On each iteration you must reason about the current state and choose exactly one tool to call next.

## USER CONTEXT
{user_context}

## SAFETY — USER ALLERGIES (NEVER SKIP)
{allergy_context}
Anaphylactic allergens MUST appear in sql_filters.exclude_allergens for any search_restaurants call.
This is non-negotiable.
{observations_text}
## CONVERSATION HISTORY
{history_text}
## CURRENT USER MESSAGE
{message}

## AVAILABLE TOOLS

search_restaurants
  Input: {{ "sql_filters": {{ "price_tiers": [...], "cuisine_types": [...], "area": "...",
             "min_rating": 4.0, "exclude_allergens": [...] }},
           "vector_query": "descriptive semantic query string" }}
  Use when: you need to find restaurants matching criteria.
  Note: if a previous observation says 0 results, broaden filters (remove area, lower price tier, etc.).

evaluate_candidates
  Input: {{ "candidate_ids": [1, 2, 3, ...] }}
  Use when: you have search results and want to score + rank them.
  Prerequisite: search_restaurants must have been called and returned results.

ask_clarification
  Input: {{ "question": "What specific question to ask the user?" }}
  Use when: the query is genuinely ambiguous and you cannot make a reasonable assumption.
  Note: prefer searching with reasonable defaults over asking.

final_response
  Input: {{ "ui_type": "restaurant_list" | "radar_comparison" | "map_view" | "text" }}
  Use when: you have enough evaluated candidates to give a useful answer.
  Note: you MUST call this to send results to the user. The loop ends after this.

## OUTPUT FORMAT
Output only valid JSON matching the schema below.
No markdown fences. No preamble. No explanation.

{{
  "thought": "Brief reasoning about current state and why you are choosing this tool",
  "tool": "search_restaurants | evaluate_candidates | ask_clarification | final_response",
  "tool_input": {{ ... }}
}}"""
