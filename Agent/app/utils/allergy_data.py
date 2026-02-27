"""
Canonical allergen definitions — single source of truth for all allergy logic.
Both the ingestion script and the runtime AllergyGuard import exclusively from here.
"""

# The 14 major EU allergens + common extras
CANONICAL_ALLERGENS = [
    "peanuts", "tree_nuts", "shellfish", "fish", "dairy", "eggs",
    "gluten", "soy", "sesame", "mustard", "celery", "lupin",
    "molluscs", "sulphites",
]

# Synonyms mapping to canonical names
ALLERGEN_SYNONYMS: dict[str, str] = {
    "nuts": "tree_nuts", "cashews": "tree_nuts", "almonds": "tree_nuts",
    "walnuts": "tree_nuts", "pistachios": "tree_nuts",
    "milk": "dairy", "cheese": "dairy", "butter": "dairy",
    "cream": "dairy", "ghee": "dairy", "paneer": "dairy",
    "lactose": "dairy", "curd": "dairy",
    "wheat": "gluten", "barley": "gluten", "rye": "gluten",
    "flour": "gluten", "maida": "gluten", "bread": "gluten",
    "prawn": "shellfish", "crab": "shellfish", "lobster": "shellfish",
    "shrimp": "shellfish", "crayfish": "shellfish",
    "oyster": "molluscs", "clam": "molluscs", "squid": "molluscs",
    "soya": "soy", "tofu": "soy", "tempeh": "soy",
    "sulfites": "sulphites", "wine": "sulphites",
    "til": "sesame", "tahini": "sesame",
    "groundnut": "peanuts", "mungfali": "peanuts",
}

# Cuisine type → likely allergens (medium confidence heuristic)
CUISINE_ALLERGEN_MAP: dict[str, list[str]] = {
    "chinese":          ["peanuts", "soy", "shellfish", "gluten", "sesame"],
    "thai":             ["peanuts", "shellfish", "fish", "soy", "sesame", "tree_nuts"],
    "japanese":         ["fish", "shellfish", "soy", "sesame", "molluscs"],
    "indian":           ["dairy", "gluten", "mustard", "tree_nuts", "sesame"],
    "south indian":     ["dairy", "mustard", "sesame"],
    "north indian":     ["dairy", "gluten", "tree_nuts"],
    "mughlai":          ["dairy", "tree_nuts", "gluten"],
    "italian":          ["gluten", "dairy", "eggs"],
    "mexican":          ["gluten", "dairy"],
    "seafood":          ["shellfish", "fish", "molluscs"],
    "mediterranean":    ["gluten", "dairy", "fish", "sesame"],
    "middle eastern":   ["sesame", "tree_nuts", "dairy", "gluten"],
    "continental":      ["dairy", "gluten", "eggs"],
    "bakery":           ["gluten", "dairy", "eggs"],
    "desserts":         ["dairy", "eggs", "gluten", "tree_nuts"],
    "biryani":          ["dairy", "gluten"],
    "street food":      ["gluten", "peanuts", "dairy"],
}

SEVERITY_LEVELS = ["anaphylactic", "severe", "moderate", "intolerance"]

# Warning templates keyed by severity — rendered directly in the UI
ALLERGY_WARNINGS: dict[str, dict[str, str]] = {
    "anaphylactic": {
        "level":   "danger",
        "emoji":   "🚨",
        "title":   "Anaphylaxis Risk",
        "message": (
            "This restaurant may contain {allergen}. Given your severe allergy, "
            "we strongly recommend calling ahead to confirm before visiting."
        ),
    },
    "severe": {
        "level":   "warning",
        "emoji":   "⚠️",
        "title":   "Allergy Warning",
        "message": (
            "This restaurant likely serves dishes containing {allergen}. "
            "Please inform the staff of your allergy when you arrive."
        ),
    },
    "moderate": {
        "level":   "caution",
        "emoji":   "⚡",
        "title":   "Heads Up",
        "message": (
            "Some dishes here may contain {allergen}. "
            "Ask your server about allergen-free options before ordering."
        ),
    },
    "intolerance": {
        "level":   "info",
        "emoji":   "ℹ️",
        "title":   "Note",
        "message": (
            "This restaurant serves dishes with {allergen}. "
            "Allergen-free options may be available — worth checking with staff."
        ),
    },
}

CONFIDENCE_NOTE = (
    "Allergen data for this restaurant is estimated from cuisine type — "
    "always confirm with staff before ordering."
)
