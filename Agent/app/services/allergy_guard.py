"""
AllergyGuard — safety layer that annotates every restaurant result with
allergy warnings and re-orders results so the safest options appear first.

This service runs on EVERY restaurant result before anything is returned
to the user. It is never optional and cannot be bypassed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.schemas.restaurant import AllergyWarning, RestaurantResult
from app.utils.allergy_data import (
    ALLERGY_WARNINGS,
    CANONICAL_ALLERGENS,
    CONFIDENCE_NOTE,
    SEVERITY_LEVELS,
)

logger = logging.getLogger(__name__)

# Severity → numeric rank (lower = safer, higher = more dangerous)
_SEVERITY_RANK = {level: i for i, level in enumerate(SEVERITY_LEVELS)}


@dataclass
class AllergyCheckResult:
    """
    Result of running AllergyGuard.check().
    safe_restaurants contains annotated results sorted safest-first.
    flagged_restaurants contains anaphylactic + high-confidence matches rendered
    in a separate danger banner at the bottom of the UI.
    """

    safe_restaurants: list[RestaurantResult] = field(default_factory=list)
    flagged_restaurants: list[RestaurantResult] = field(default_factory=list)
    has_any_warnings: bool = False


class AllergyGuard:
    """
    Safety layer: annotates every recommended restaurant with allergy warnings
    and re-orders results so the safest options appear first.

    Core rules:
    1. Never silently hide a restaurant due to allergies — always show it with
       a clear warning so the user can make an informed decision.
    2. Exception: if severity is 'anaphylactic' AND allergen_confidence is
       'high', move that restaurant into flagged_restaurants, clearly labelled
       as high-risk.
    3. Sort output: allergy_safe=True first, then by worst-case severity
       (intolerance → moderate → severe → anaphylactic last).
    4. Warning language must match severity — never alarm for an intolerance,
       never soft-pedal an anaphylactic risk.
    5. Always add a confidence_note when allergen_confidence != 'high'.
    """

    def check(
        self,
        restaurants: list[RestaurantResult],
        user_allergies: dict[str, Any],
    ) -> AllergyCheckResult:
        """
        Annotate restaurants with allergy warnings and split into safe/flagged lists.

        Returns AllergyCheckResult with:
          safe_restaurants: annotated, sorted safe-first
          flagged_restaurants: anaphylactic + high confidence only
          has_any_warnings: True if any warnings exist
        """
        confirmed: list[str] = user_allergies.get("confirmed", [])
        intolerances: list[str] = user_allergies.get("intolerances", [])
        severity_map: dict[str, str] = user_allergies.get("severity", {})

        # Combine all allergens the user has flagged
        all_user_allergens = {a: severity_map.get(a, "severe") for a in confirmed}
        for intol in intolerances:
            all_user_allergens.setdefault(intol, "intolerance")

        safe_list: list[RestaurantResult] = []
        flagged_list: list[RestaurantResult] = []
        has_any = False

        for restaurant in restaurants:
            annotated = self._annotate(restaurant, all_user_allergens)
            if annotated.allergy_warnings:
                has_any = True

            # Rule 2: anaphylactic + high confidence → flagged list
            is_flagged = any(
                w.severity == "anaphylactic" and w.confidence == "high"
                for w in annotated.allergy_warnings
            )
            if is_flagged:
                flagged_list.append(annotated)
            else:
                safe_list.append(annotated)

        # Sort safe_list: allergy_safe first, then worst severity last
        safe_list.sort(key=self._sort_key)

        return AllergyCheckResult(
            safe_restaurants=safe_list,
            flagged_restaurants=flagged_list,
            has_any_warnings=has_any,
        )

    def _annotate(
        self,
        restaurant: RestaurantResult,
        user_allergens: dict[str, str],
    ) -> RestaurantResult:
        """Build allergy_warnings for a single restaurant and mark allergy_safe."""
        warnings: list[AllergyWarning] = []
        restaurant_allergens = set(restaurant.known_allergens)

        for allergen, user_severity in user_allergens.items():
            if allergen in restaurant_allergens:
                warning = self.build_warning(
                    allergen=allergen,
                    severity=user_severity,
                    confidence=restaurant.allergen_confidence,
                )
                warnings.append(warning)

        # Sort warnings: most severe first
        warnings.sort(
            key=lambda w: _SEVERITY_RANK.get(w.severity, 0), reverse=True
        )

        allergy_safe = len(warnings) == 0

        # Return a copy with allergy annotation attached
        return restaurant.model_copy(
            update={"allergy_warnings": warnings, "allergy_safe": allergy_safe}
        )

    def build_warning(
        self,
        allergen: str,
        severity: str,
        confidence: str,
    ) -> AllergyWarning:
        """
        Build a structured AllergyWarning from the canonical template.

        If confidence != 'high', appends a confidence_note explaining that
        allergen data was estimated from cuisine type heuristics.
        """
        # Normalise severity to a known level; default to 'severe'
        if severity not in _SEVERITY_RANK:
            severity = "severe"

        template = ALLERGY_WARNINGS[severity]
        message = template["message"].format(allergen=allergen)
        confidence_note = CONFIDENCE_NOTE if confidence != "high" else None

        return AllergyWarning(
            allergen=allergen,
            severity=severity,
            level=template["level"],
            emoji=template["emoji"],
            title=template["title"],
            message=message,
            confidence=confidence,
            confidence_note=confidence_note,
        )

    @staticmethod
    def _sort_key(restaurant: RestaurantResult) -> tuple[int, int]:
        """
        Sort key: (is_unsafe, worst_severity_rank).
        allergy_safe=True → 0, unsafe → 1.
        Within unsafe: sorted by worst-case severity ascending (intolerance first).
        """
        if restaurant.allergy_safe:
            return (0, 0)
        worst_rank = max(
            (_SEVERITY_RANK.get(w.severity, 0) for w in restaurant.allergy_warnings),
            default=0,
        )
        return (1, worst_rank)
