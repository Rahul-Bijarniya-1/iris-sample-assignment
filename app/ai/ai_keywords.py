# ==========================================================
# AI Advisor Vocabulary
# ==========================================================

HELP_TERMS = {
    "help",
    "guide",
    "examples",
    "commands",
    "what can you do",
    "capabilities",
    "features",
}

CITY_TERMS = {
    "city",
    "cities",
    "in",
    "located in",
    "within",
    "around",
}

FACILITY_TERMS = {
    "facility",
    "facilities",
    "site",
    "sites",
    "data center",
    "data centers",
    "datacenter",
    "datacenters",
    "data centre",
    "data centres",
    "colo",
    "colocation",
}

COMPANY_TERMS = {
    "company",
    "operator",
    "provider",
    "owner",
}

COMPARE_TERMS = {
    "compare",
    "comparison",
    "difference",
    "vs",
    "versus",
    "against",
}

RANKING_TERMS = {
    "top",
    "best",
    "highest",
    "lowest",
    "rank",
    "ranking",
    "leading",
}

POWER_TERMS = {
    "grid",
    "substation",
    "transformer",
    "transmission",
    "voltage",
    "power",
    "electricity",
}

LAND_TERMS = {
    "land",
    "land value",
    "price",
    "cost",
    "municipality",
    "property",
}

RENEWABLE_TERMS = {
    "renewable",
    "solar",
    "wind",
    "green",
    "esg",
    "sustainability",
}

EXPANSION_TERMS = {
    "expand",
    "expansion",
    "future",
    "growth",
    "capacity",
}

NEARBY_TERMS = [

    "near",

    "nearby",

    "around",

    "within",

    "close to",

    "radius",

    "km",

    "kilometer",

    "kilometers",
]

NEWS_TERMS = [

    "news",
    "signal",
    "signals",
    "recent",
    "latest",

    "investment",
    "investments",
    "invested",

    "expansion",
    "expand",
    "expanded",

    "announcement",
    "announcements",

    "retrofit",

    "press",

    "media",

    "activity",
    "activities",

    "market",

    "acquisition",
    "acquired",

    "operator updates",

    "industry",

    "headline",
    "headlines",
]


# Function words that should never make a full-question news search match.
# Kept with the rest of the advisor vocabulary so intent and search terms
# have one source of truth.
NEWS_SEARCH_STOPWORDS = {
    "what",
    "whats",
    "the",
    "and",
    "for",
    "are",
    "was",
    "has",
    "about",
    "near",
    "with",
    "from",
    "that",
    "this",
    "there",
    "should",
    "know",
    "happening",
    "recent",
    "activity",
    "have",
    "were",
    "die",
    "der",
    "das",
    "und",
    "ist",
    "sind",
    "mit",
    "fuer",
}
