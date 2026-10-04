"""
Vocabist — Content Expansion P1: Build the Vocabulary Brain
============================================================
Expands the canonical vocabulary corpus from ~231 to ~1,000 words.

Uses the existing content pipeline:
  - AI generation via Emergent LLM key (gpt-5.6-luna)
  - Ingestion via content_ingest.ingest_word()
  - Validation via content_validation.validate_word()
  - Canonical schema (vocab_schema.py)
  - Provenance: AI_GENERATED
  - Lifecycle: REVIEW (per pipeline rules; promoted after validation)

Run from /app/backend:
    python expand_vocabulary.py

Safety:
  - Never deletes existing words
  - Never overwrites published content
  - Deduplicates via canonical_key
  - All words pass validation before persistence
  - Failures are recorded, not fatal
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BACKEND_DIR, ".env"))

from emergentintegrations.llm.chat import LlmChat, UserMessage
from vocab_schema import normalize_headword
from content_ingest import ingest_word, bulk_ingest

KEY = os.environ["EMERGENT_LLM_KEY"]

TOPICS = ["academic", "everyday", "business", "science", "emotions", "society"]
EXAMS = ["ielts", "toefl", "gre", "sat", "gmat", "cefr"]
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# ------------------------------------------------------------------ #
# Curated word lists by CEFR — high-frequency, learner-useful words
# ------------------------------------------------------------------ #

# These are deliberately chosen for learning value, not randomly generated.
# Each list targets gaps in the current corpus.

WORD_LISTS: Dict[str, List[str]] = {
    "A1": [
        # Everyday basics
        "apple", "baby", "bag", "ball", "banana", "bath", "bed", "beer", "big",
        "bird", "black", "blue", "boat", "body", "book", "bottle", "box", "boy",
        "bread", "breakfast", "brother", "bus", "cake", "car", "cat", "chair",
        "cheese", "chicken", "child", "city", "clock", "close", "clothes", "coffee",
        "color", "cook", "country", "cup", "dance", "daughter", "day", "dinner",
        "doctor", "dog", "door", "drink", "drive", "eat", "egg", "evening",
        "eye", "face", "family", "father", "fish", "flower", "food", "foot",
        "game", "garden", "girl", "glass", "good", "green", "hair", "hand",
        "house", "husband", "juice", "key", "kitchen", "letter", "light", "listen",
        "lunch", "man", "milk", "money", "month", "morning", "mother", "music",
        "name", "night", "number", "orange", "park", "pen", "phone", "picture",
        "play", "rain", "read", "red", "rice", "river", "road", "room",
        "run", "school", "sea", "shirt", "shop", "sister", "sit", "sleep",
        "small", "snow", "son", "speak", "stand", "stop", "street", "sun",
        "swim", "table", "talk", "tea", "teacher", "ticket", "today", "train",
        "tree", "walk", "wall", "watch", "water", "week", "white", "wife",
        "window", "woman", "work", "write", "year", "young",
    ],
    "A2": [
        # Elementary vocabulary
        "accident", "across", "address", "afternoon", "agree", "airport", "almost",
        "alone", "already", "also", "always", "another", "apartment", "area",
        "argue", "army", "art", "ask", "aunt", "autumn", "beach", "become",
        "begin", "behind", "believe", "between", "birthday", "blood", "boring",
        "born", "bottom", "bridge", "bright", "broken", "building", "burn",
        "careful", "catch", "cause", "century", "chance", "check", "church",
        "circle", "climb", "cloud", "college", "common", "compare", "complete",
        "concert", "cook", "corner", "count", "couple", "cousin", "cover",
        "cross", "crowd", "cry", "culture", "dangerous", "dark", "dead",
        "decide", "deep", "describe", "desert", "develop", "different", "difficult",
        "direction", "dirty", "dream", "dress", "drop", "during", "earth",
        "east", "edge", "education", "electric", "empty", "end", "enough",
        "enter", "escape", "exact", "example", "exercise", "expect", "explain",
        "famous", "farm", "fast", "fat", "favorite", "feel", "fight", "fill",
        "final", "find", "finger", "finish", "fire", "flat", "fly", "follow",
        "forest", "fresh", "front", "full", "future", "gentle", "gift", "glad",
        "gold", "grade", "grandparent", "grass", "guess", "half", "hang",
        "happen", "health", "heart", "heavy", "hide", "high", "hill", "hole",
        "holiday", "homework", "honest", "hospital", "hotel", "huge", "hungry",
        "hurry", "hurt", "idea", "ill", "imagine", "important", "inside",
        "instead", "interest", "island", "journey", "keep", "kill", "knee",
        "lake", "land", "language", "late", "laugh", "lazy", "lead",
        "leaf", "leave", "less", "library", "lie", "lift", "list",
        "loud", "low", "luck", "machine", "magazine", "main", "map",
        "marry", "meal", "mean", "meet", "middle", "mind", "mirror",
        "miss", "mix", "modern", "mountain", "narrow", "nature", "near",
        "neck", "need", "neighbor", "noise", "normal", "north", "notice",
        "ocean", "offer", "old", "opinion", "outside", "pain", "paint",
        "palace", "parent", "path", "peace", "perfect", "period", "pick",
        "piece", "planet", "plastic", "pocket", "point", "polite", "poor",
        "position", "possible", "power", "practice", "prepare", "pretty",
        "private", "problem", "produce", "program", "promise", "pull", "push",
        "put", "quick", "quiet", "reach", "ready", "real", "reason",
        "receive", "record", "refuse", "region", "remember", "rest",
        "rich", "ring", "rock", "round", "rule", "safe", "sand",
        "save", "science", "secret", "seem", "send", "serious", "serve",
        "share", "sharp", "shine", "shoe", "short", "shoulder", "shout",
        "show", "shut", "sick", "side", "sign", "silent", "simple",
        "since", "sing", "size", "skill", "skin", "sky", "slow",
        "smoke", "soft", "soil", "soldier", "solve", "soon", "sort",
        "sound", "south", "space", "special", "speed", "spend", "sport",
        "square", "stage", "stair", "star", "start", "station", "stay",
        "steal", "step", "stick", "stone", "storm", "story", "straight",
        "strange", "strong", "stupid", "sugar", "sure", "taste", "thick",
        "thin", "throw", "tired", "touch", "tour", "toward", "tower",
        "town", "trade", "travel", "trouble", "trust", "try", "turn",
        "twice", "type", "ugly", "uncle", "under", "understand", "uniform",
        "unit", "until", "upon", "useful", "usual", "vacation", "valley",
        "value", "village", "visit", "voice", "wait", "wake", "warn",
        "wash", "waste", "wave", "weak", "wear", "weather", "weight",
        "welcome", "west", "whole", "wide", "wild", "win", "wind",
        "wish", "wonder", "wood", "wool", "word", "world", "wrong",
    ],
    "B1": [
        # Intermediate — practical communication
        "abandon", "ability", "absence", "absorb", "abstract", "accept", "access",
        "accommodate", "accompany", "accomplish", "account", "accurate", "accuse",
        "achieve", "acknowledge", "acquire", "adapt", "adequate", "adjust",
        "admire", "admit", "adopt", "advance", "advantage", "advertise", "affair",
        "affect", "agenda", "aggressive", "aid", "aim", "alarm", "allow",
        "amount", "announce", "annual", "anxiety", "apparent", "appeal",
        "appearance", "apply", "appreciate", "approach", "appropriate", "approve",
        "arrange", "arrest", "aspect", "assume", "atmosphere", "attach", "attack",
        "attempt", "attend", "attention", "attitude", "attract", "authority",
        "available", "average", "avoid", "award", "aware", "background",
        "balance", "ban", "barrier", "base", "basic", "bear", "beat",
        "behavior", "belong", "benefit", "blame", "blind", "block", "bomb",
        "bond", "bone", "boost", "border", "bother", "bound", "brain",
        "brand", "brave", "brief", "broad", "broadcast", "budget", "burden",
        "cabinet", "calculate", "campaign", "cancel", "capable", "capital",
        "capture", "career", "celebrate", "ceremony", "challenge", "champion",
        "channel", "chapter", "characteristic", "charity", "chemical", "chief",
        "circumstance", "claim", "classic", "climate", "coach", "coalition",
        "code", "collapse", "colleague", "column", "combine", "comfort",
        "command", "comment", "commit", "committee", "communicate", "companion",
        "complaint", "complex", "component", "concentrate", "concept", "concern",
        "conclude", "condition", "conduct", "confidence", "confirm", "conflict",
        "confuse", "connect", "conscious", "consequence", "conservative", "consist",
        "constant", "construct", "consult", "contain", "content", "context",
        "contract", "contrast", "contribute", "control", "convenient", "convention",
        "conversation", "convince", "cope", "core", "corporate", "council",
        "courage", "crash", "create", "credit", "crime", "crisis", "critic",
        "crop", "crowd", "crucial", "cure", "curious", "current", "curve",
        "damage", "dare", "database", "deadline", "debate", "debt", "decade",
        "decline", "decrease", "defeat", "defend", "delay", "deliver",
        "demand", "democracy", "demonstrate", "deny", "department", "depend",
        "depression", "despite", "destroy", "detect", "determine", "device",
        "devote", "dialogue", "diet", "digital", "dimension", "disaster",
        "discipline", "discount", "discuss", "disease", "display", "distance",
        "distinction", "distribute", "district", "disturb", "document", "domestic",
        "dominate", "donate", "doubt", "downtown", "dramatic", "dust",
        "duty", "eager", "earn", "economy", "edition", "effective",
        "efficient", "effort", "elect", "element", "eliminate", "emerge",
        "emotion", "emphasis", "employ", "enable", "encourage", "engage",
        "enormous", "ensure", "entire", "entrance", "episode", "establish",
        "estimate", "evaluate", "eventually", "evolve", "examine", "exceed",
        "excellent", "exception", "exchange", "exclusive", "exhibit", "exist",
        "expand", "expense", "expert", "explore", "export", "expose",
        "extend", "extent", "extreme", "facility", "factor", "failure",
        "fairly", "faith", "familiar", "fantasy", "fashion", "fate",
        "fault", "favor", "feature", "federal", "fiction", "figure",
        "finance", "firm", "fix", "flexible", "flight", "float",
        "flood", "flow", "focus", "fold", "folk", "forbid",
        "forecast", "foreign", "formal", "former", "formula", "fortune",
        "foundation", "frame", "frequent", "fuel", "fulfill", "function",
        "fund", "fundamental", "gain", "gap", "gather", "gender",
        "generate", "generous", "genius", "genuine", "global", "goods",
        "govern", "grab", "graduate", "grand", "grant", "guarantee",
        "guard", "guide", "guilty", "handle", "harbor", "harm",
        "harsh", "heal", "highlight", "host", "household", "humor",
        "hunt", "ideal", "identify", "ignore", "illustrate", "image",
        "immediate", "impact", "implement", "import", "impose", "impress",
        "improve", "incident", "include", "income", "independent", "index",
        "indicate", "individual", "industrial", "industry", "influence",
        "inform", "initial", "injury", "inner", "innocent", "innovation",
        "input", "inquiry", "insist", "inspire", "install", "instance",
        "instrument", "insurance", "intellectual", "intend", "intense",
        "intention", "invest", "investigate", "involve", "issue", "item",
        "justify", "labor", "lack", "launch", "layer", "lean",
        "lecture", "legal", "leisure", "liberal", "license", "limit",
        "link", "literature", "load", "loan", "local", "locate",
        "logic", "loose", "loss", "luxury", "manner", "manufacture",
        "massive", "master", "material", "mayor", "meanwhile", "measure",
        "media", "mental", "merely", "mess", "minority", "mission",
        "mode", "modify", "monitor", "mood", "moral", "motion",
        "motivate", "mutual", "mystery", "myth", "negative", "network",
        "neutral", "nevertheless", "notion", "novel", "nuclear", "numerous",
        "objective", "obligation", "obtain", "obvious", "occupy", "occur",
        "offend", "official", "operate", "oppose", "option", "organic",
        "organize", "origin", "outcome", "output", "overcome", "owe",
        "participate", "passion", "patient", "pattern", "peak", "pension",
        "perceive", "permit", "perspective", "phrase", "physical", "pitch",
        "plate", "plenty", "plot", "plug", "poem", "policy",
        "portion", "portrait", "possess", "potential", "poverty",
        "precise", "predict", "preference", "preserve", "press", "pretend",
        "prevent", "primarily", "prime", "principle", "prior", "priority",
        "proceed", "process", "profession", "profit", "promote", "proof",
        "proportion", "propose", "prospect", "protest", "prove", "provide",
        "province", "psychological", "publish", "purchase", "pursue", "qualify",
        "quarter", "quote", "race", "radical", "random", "range",
        "rank", "rapid", "rare", "rate", "raw", "react",
        "reality", "recognize", "recommend", "recover", "reduce", "reflect",
        "reform", "regard", "regime", "release", "relevant", "relief",
        "religion", "rely", "remark", "remote", "remove", "renew",
        "replace", "represent", "republic", "reputation", "request", "require",
        "rescue", "reserve", "resident", "resist", "resolve", "resource",
        "respond", "restore", "restrict", "retain", "retire", "reveal",
        "reverse", "revolution", "reward", "rhythm", "riot", "risk",
        "rival", "role", "root", "rough", "rural", "rush",
        "sacrifice", "satisfy", "scale", "scatter", "scenario", "scheme",
        "scholar", "scope", "screen", "sector", "secure", "seek",
        "select", "senior", "sensitive", "separate", "sequence", "session",
        "settle", "severe", "shadow", "shape", "shift", "shock",
        "signal", "significant", "similar", "slight", "slip", "smart",
        "smooth", "snap", "solution", "somewhat", "source", "spare",
        "specific", "spin", "split", "sponsor", "spot", "spread",
        "stable", "staff", "standard", "status", "steady", "steel",
        "stem", "stimulus", "stock", "strategy", "strength", "stress",
        "stretch", "strike", "strip", "struggle", "submit", "substance",
        "substitute", "succeed", "suggestion", "suit", "summit", "super",
        "surface", "surgery", "surround", "survive", "suspect", "suspend",
        "sustain", "switch", "symbol", "sympathy", "target", "task",
        "tax", "technique", "temperature", "tend", "tension", "term",
        "territory", "theme", "therapy", "threat", "thus", "tight",
        "tip", "tone", "total", "tough", "trace", "track",
        "transfer", "transform", "transition", "trap", "treasure", "treat",
        "trend", "trial", "tribe", "trick", "trigger", "triumph",
        "troop", "trust", "tube", "typical", "ultimate", "undergo",
        "undertake", "unite", "universal", "upper", "urban", "urge",
        "vast", "vehicle", "venture", "version", "victim", "violent",
        "virtual", "vision", "vital", "volume", "voluntary", "wage",
        "weapon", "web", "weird", "whereas", "widespread", "witness",
        "workplace", "workshop", "wound", "wrap", "yield", "zone",
    ],
    "B2": [
        # Upper-intermediate — fluency & nuance
        "abolish", "absorb", "abundance", "accessible", "accumulate", "accustom",
        "acquaintance", "acute", "adhere", "adjacent", "administration", "adolescent",
        "adverse", "aesthetic", "affiliation", "affluent", "aggravate", "alleviate",
        "ally", "alter", "ambition", "ample", "analogy", "anchor",
        "anonymous", "anticipate", "apathy", "apparatus", "applaud", "apt",
        "arbitrary", "aspiration", "assert", "asset", "assumption", "assurance",
        "audacity", "authentic", "autonomy", "averse", "bankrupt", "bargain",
        "benchmark", "beneficiary", "bias", "bind", "blueprint", "bold",
        "boom", "breach", "breakthrough", "breed", "brutal", "bulk",
        "bureaucracy", "capacity", "carbon", "cater", "caution", "cede",
        "chronic", "civic", "clarify", "clash", "clause", "cognitive",
        "coincidence", "commodity", "compensate", "competence", "complement",
        "compliance", "compromise", "compulsory", "concede", "conceive", "concrete",
        "condemn", "consensus", "contemplate", "contentious", "contradict", "controversy",
        "conversion", "convey", "coordinate", "counterpart", "craft", "credible",
        "curb", "curriculum", "customary", "cynical", "database", "debris",
        "deceive", "deficiency", "delegate", "deliberate", "demographic", "depict",
        "deploy", "deprive", "derive", "designate", "despair", "detain",
        "deter", "deviate", "diagnose", "dimension", "diminish", "discard",
        "disclose", "discourse", "discrete", "disparity", "displace", "dispose",
        "disregard", "disrupt", "dissolve", "distinct", "distort", "distress",
        "dividend", "doctrine", "dominant", "donor", "downfall", "draft",
        "drastic", "dwell", "dynamic", "elaborate", "embrace", "emission",
        "empathy", "endeavor", "endorse", "enforce", "enhance", "enterprise",
        "entitle", "entrepreneur", "envision", "equity", "erode", "essence",
        "ethical", "evoke", "exaggerate", "excerpt", "execute", "exempt",
        "exile", "exploit", "expose", "extract", "fabricate", "facet",
        "facilitate", "faculty", "famine", "fatigue", "feasibility", "feat",
        "fiscal", "flaw", "flee", "fluctuate", "forbid", "forge",
        "formidable", "forthcoming", "foster", "fraction", "fragile", "fraud",
        "friction", "frontier", "fulfillment", "fury", "futile", "generic",
        "genocide", "grasp", "grave", "grip", "gross", "habitat",
        "halt", "handicap", "hazard", "heritage", "hierarchy", "hinder",
        "hostile", "humanitarian", "humble", "hypocrisy", "ideology", "illusion",
        "immense", "immigrant", "immune", "impair", "imperative", "implicit",
        "impulse", "incentive", "incidence", "inclination", "incorporate", "incur",
        "induce", "infer", "inflate", "infrastructure", "inherent", "inhibit",
        "initiative", "inject", "insight", "integral", "integrity", "intercept",
        "interim", "intervene", "intimate", "intrinsic", "invade", "inventory",
        "invoke", "irony", "isolation", "jeopardize", "jurisdiction", "keen",
        "lag", "landmark", "legitimate", "leverage", "liable", "likelihood",
        "likewise", "linger", "literacy", "lobby", "log", "longevity",
        "magnitude", "mainstream", "mandatory", "manifest", "manipulate", "margin",
        "mature", "mediate", "merge", "merit", "metabolism", "migrate",
        "militant", "minimal", "mobility", "monopoly", "motive", "municipal",
        "navigate", "neglect", "niche", "norm", "notably", "notwithstanding",
        "nutrition", "obstacle", "offset", "omit", "onset", "opaque",
        "optimism", "opt", "orient", "outbreak", "outline", "outweigh",
        "overlap", "oversee", "oversight", "overturn", "overwhelm", "paradox",
        "parallel", "parliament", "patent", "pathology", "peer", "penalty",
        "penetrate", "persist", "petition", "pioneer", "plea", "plead",
        "pledge", "plunge", "portfolio", "portray", "pose", "precaution",
        "precede", "predecessor", "premise", "premium", "prevalent", "probe",
        "procurement", "profound", "prohibit", "projection", "prominent", "prone",
        "propaganda", "prosecute", "prospective", "provincial", "provision", "provoke",
        "proximity", "quota", "radical", "rally", "rationale", "realm",
        "rebound", "recession", "reckon", "reconciliation", "referendum", "refine",
        "reinforce", "reluctant", "remedy", "render", "renowned", "reproduce",
        "resemble", "reside", "respective", "restoration", "restraint", "revise",
        "rhetoric", "robust", "sanction", "secular", "sensation", "sentiment",
        "setback", "shrink", "simulate", "skeptical", "solely", "solidarity",
        "sovereign", "span", "spark", "specification", "spectacle", "speculate",
        "sphere", "sprawl", "stance", "stark", "static", "statute",
        "steep", "stereotype", "stimulate", "strand", "subsidiary", "subtle",
        "successor", "supplement", "suppress", "surge", "surplus", "susceptible",
        "suspension", "swift", "syndrome", "tactical", "tangible", "terminate",
        "testament", "threshold", "thrive", "toll", "toxic", "trait",
        "transparent", "trauma", "treaty", "tremendous", "trivial", "turbulence",
        "turnover", "unanimous", "underlying", "undermine", "undoubtedly", "unfold",
        "unprecedented", "unrest", "uphold", "utility", "vague", "valid",
        "vanish", "venture", "verdict", "viable", "vigorous", "violation",
        "virtue", "volatile", "vulnerability", "warrant", "wield", "yield",
    ],
    "C1": [
        # Advanced — academic & professional
        "abdicate", "abridge", "abstain", "accentuate", "accrue", "acquiesce",
        "acrimonious", "adamant", "adept", "adjudicate", "admonish", "adversary",
        "affidavit", "aggrandize", "albeit", "allegation", "allude", "amalgamate",
        "ameliorate", "amend", "amicable", "annotate", "antagonist", "apex",
        "appease", "apportion", "appraise", "archaic", "arduous", "articulate",
        "ascertain", "assail", "assimilate", "attest", "augment", "austere",
        "authenticate", "avert", "axiomatic", "belligerent", "benevolent", "bequeath",
        "bewilder", "bolster", "brevity", "broach", "bureaucratic", "burgeon",
        "calibrate", "capitulate", "catapult", "caustic", "cessation", "circumscribe",
        "clandestine", "clemency", "coalesce", "coerce", "cogent", "collaborate",
        "collateral", "commemorate", "commensurate", "compel", "complacent", "compliant",
        "concealment", "condone", "confiscate", "confluence", "congenial", "conjecture",
        "connote", "conscientious", "consolidate", "conspicuous", "constituent",
        "constrain", "consummate", "contempt", "contingency", "contravene", "convene",
        "convergence", "copious", "correlate", "culminate", "culpable", "curtail",
        "daunting", "debilitate", "decorum", "deem", "defamation", "defer",
        "deficit", "degradation", "deleterious", "delineate", "denounce", "deplete",
        "depreciate", "derelict", "derogatory", "desist", "detrimental", "devoid",
        "dexterity", "dichotomy", "diffuse", "dilemma", "discern", "discord",
        "discretion", "disdain", "disintegrate", "dismay", "dispel", "disposition",
        "disrepute", "disseminate", "dissent", "diverge", "divulge", "dormant",
        "dubious", "eclipse", "edifice", "efficacy", "elicit", "embark",
        "eminent", "encompass", "endow", "engender", "enigma", "enmity",
        "ensue", "entail", "epitome", "equitable", "erratic", "espouse",
        "esteem", "evade", "exacerbate", "exalt", "exemplary", "exemplify",
        "exert", "exodus", "expedite", "explicit", "exponent", "expound",
        "exquisite", "extravagant", "extricate", "facetious", "fallacy", "fervent",
        "fidelity", "flagrant", "fluctuation", "foreboding", "forestall", "formulate",
        "fortify", "fraught", "frivolous", "frugal", "futility", "galvanize",
        "garnish", "gratuitous", "grievance", "hamper", "harbinger", "heed",
        "hegemony", "heresy", "hypothetical", "idiosyncratic", "imminent", "impasse",
        "impede", "impervious", "implicate", "impromptu", "impunity", "incite",
        "inclusive", "incoherent", "incumbent", "indelible", "indigenous", "indiscriminate",
        "infallible", "inflammatory", "influx", "infringe", "ingenious", "innate",
        "innocuous", "insidious", "insinuate", "instigate", "intangible", "interject",
        "intermittent", "interplay", "interrogate", "intrepid", "inundate", "invalidate",
        "invert", "invoke", "irreconcilable", "irreversible", "itinerant",
        "juxtapose", "languish", "laudable", "lax", "levy", "liaison",
        "litigate", "lucid", "lure", "magnate", "malice", "mandate",
        "manifesto", "meander", "mediocre", "mercenary", "meritorious", "metamorphosis",
        "mitigate", "mobilize", "mollify", "moratorium", "nascent", "negligent",
        "negate", "nominal", "nonchalant", "nuance", "nullify", "obliterate",
        "obscure", "obstruct", "omnipresent", "onerous", "opulent", "ornate",
        "oscillate", "ostentatious", "oust", "overhaul", "palpable", "paradoxical",
        "paramount", "partisan", "patronize", "pedagogy", "pejorative", "penchant",
        "perilous", "perjury", "permeable", "perpetuate", "pertinent", "pervasive",
        "pinnacle", "placate", "plausible", "plight", "pragmatism", "precarious",
        "precedent", "precipitate", "preemptive", "prejudicial", "prerogative", "prevail",
        "proficient", "proliferate", "propensity", "propriety", "proscribe", "provisional",
        "prudence", "purport", "quandary", "quell", "ramification", "ratify",
        "rebuke", "recalcitrant", "reciprocal", "reclusive", "redeem", "redundant",
        "refute", "reimburse", "reiterate", "relinquish", "remit", "repeal",
        "repercussion", "replenish", "reprimand", "repudiate", "requisite", "rescind",
        "residual", "restitution", "retract", "retrospect", "revoke", "rudimentary",
        "sacrosanct", "salient", "scrutiny", "sedentary", "seminal", "sequester",
        "solicit", "solemn", "sporadic", "squander", "stagnate", "steadfast",
        "stigma", "stipulate", "stringent", "subdue", "subjective", "subordinate",
        "subversive", "succinct", "succumb", "superficial", "supersede", "supplant",
        "surrogate", "susceptibility", "synonymous", "taboo", "tacit", "tantamount",
        "tenuous", "testament", "transgression", "transient", "traverse", "turmoil",
        "ubiquity", "unambiguous", "unprecedented", "unscrupulous", "uphold", "usurp",
        "utmost", "venerate", "verbose", "veto", "vindicate", "vociferous",
        "volition", "wane", "warrant", "zealous",
    ],
    "C2": [
        # Proficiency — sophisticated & nuanced
        "abnegate", "abrogate", "abstemious", "abstruse", "accolade", "acrimony",
        "adjunct", "adroit", "adulation", "aegis", "affable", "affront",
        "alchemy", "alleviation", "altruism", "amalgam", "ambivalence", "amelioration",
        "anachronism", "anarchy", "animus", "antecedent", "antipathy", "apocryphal",
        "apotheosis", "approbation", "archetype", "ascetic", "aspersion", "assiduity",
        "assuage", "atrophy", "avarice", "aver", "baroque", "bastion",
        "beatitude", "beleaguered", "bellicose", "benediction", "beneficence", "benign",
        "berate", "bombastic", "bourgeois", "buttress", "cabal", "cacophony",
        "calumny", "capitulation", "capricious", "carte-blanche", "castigate",
        "cerebral", "chagrin", "chicanery", "circumlocution", "clamor", "clairvoyant",
        "cognizant", "commencement", "compendium", "concatenation", "concomitant",
        "conflagration", "connoisseur", "consternation", "conundrum", "convivial",
        "corpulent", "corroboration", "credulity", "culpability", "cupidity",
        "dearth", "debacle", "decadence", "defenestration", "deference", "deluge",
        "demagogue", "demeanor", "denigrate", "denouement", "deprecate",
        "despot", "diatribe", "didactic", "dilettante", "diminution", "disabuse",
        "discrepancy", "disingenuous", "disquisition", "dissolution", "doctrinaire",
        "ebullient", "eclectic", "edification", "effervescent", "effrontery", "egalitarian",
        "egregious", "elegiac", "elocution", "emanate", "emancipation", "enervate",
        "ephemeral", "equanimity", "equivocate", "erudite", "esoteric",
        "euphemism", "evanescent", "excoriate", "exculpate", "execrable", "exegesis",
        "expatriate", "expediency", "extemporaneous", "extenuate", "facile",
        "fastidious", "feckless", "felicitous", "firebrand", "fledgling", "florid",
        "fortuitous", "fulcrum", "fulminate", "garrulous", "grandiloquent",
        "gregarious", "harangue", "hubris", "iconoclast", "ignominy",
        "imbroglio", "immutable", "impartial", "impecunious", "imperious",
        "imperturbable", "impetuous", "implacable", "impregnable", "incandescent",
        "inchoate", "incontrovertible", "incredulity", "indefatigable", "ineffable",
        "inexorable", "ingratiate", "inscrutable", "insipid", "intractable",
        "intransigent", "invective", "inveterate", "irascible", "jocund",
        "juggernaut", "laconic", "largesse", "lassitude", "latent", "legerdemain",
        "magnanimous", "malfeasance", "malleable", "mendacious", "mercurial",
        "meretricious", "milieu", "misanthrope", "munificent", "nemesis",
        "nefarious", "nihilism", "nomenclature", "nondescript", "obdurate",
        "obfuscate", "oblique", "obsequious", "obstinate", "officious", "ominous",
        "opprobrium", "panacea", "panegyric", "paragon", "pariah",
        "parsimonious", "pedantic", "penitent", "penurious", "perfunctory",
        "perspicacious", "pertinacious", "petulant", "philistine", "phlegmatic",
        "platitude", "plethora", "polemic", "portentous", "posthumous",
        "precept", "precipitous", "precocious", "predilection", "preeminent",
        "preponderance", "prevaricate", "prodigious", "profligate", "prolix",
        "propitious", "prosaic", "protagonist", "protean", "proviso",
        "pugnacious", "pulchritude", "pusillanimous", "quagmire", "querulous",
        "quintessential", "quixotic", "raconteur", "recidivism", "recondite",
        "redoubtable", "refractory", "remonstrate", "reparation", "replete",
        "reprobate", "requisition", "resilience", "resplendent", "reticent",
        "sagacious", "sanctimonious", "sanguine", "sardonic", "scrupulous",
        "sedulous", "shibboleth", "sinecure", "soliloquy", "sophistry",
        "soporific", "specious", "spurious", "stolid", "strident",
        "surreptitious", "sycophant", "tautology", "temerity", "tempestuous",
        "tendentious", "torpid", "tractable", "trenchant", "trepidation",
        "truculent", "tumultuous", "turgid", "unconscionable", "unctuous",
        "unequivocal", "untenable", "venal", "venerable", "veracious",
        "veracity", "vicissitude", "vitriolic", "vituperate", "voracious",
        "zeitgeist",
    ],
}

# Confusing word pairs — these must be cross-referenced
CONFUSING_PAIRS = [
    ("affect", "effect"), ("accept", "except"), ("advice", "advise"),
    ("principal", "principle"), ("complement", "compliment"), ("stationary", "stationery"),
    ("lose", "loose"), ("than", "then"), ("their", "there"),
    ("discrete", "discreet"), ("emigrate", "immigrate"), ("elicit", "illicit"),
    ("precede", "proceed"), ("ensure", "insure"), ("imply", "infer"),
    ("allude", "elude"), ("averse", "adverse"), ("amoral", "immoral"),
    ("cite", "site"), ("council", "counsel"), ("eminent", "imminent"),
    ("flaunt", "flout"), ("historic", "historical"), ("persecute", "prosecute"),
    ("proscribe", "prescribe"), ("tortuous", "torturous"), ("censure", "censor"),
    ("contemptible", "contemptuous"), ("definite", "definitive"),
    ("disinterested", "uninterested"), ("economic", "economical"),
    ("ingenious", "ingenuous"), ("judicial", "judicious"),
]

SCHEMA_PROMPT = """Return ONLY a valid JSON array (no markdown, no code fences, no prose). Each element:
{
 "headword": "single lowercase english word",
 "phonetic": "/IPA/",
 "phonetic_us": "/US IPA/",
 "phonetic_uk": "/UK IPA/",
 "part_of_speech": "noun|verb|adjective|adverb",
 "cefr": "<ASSIGNED_LEVEL>",
 "simple_definition": "one clear learner-friendly sentence",
 "easy_meaning": "2-4 word plain meaning",
 "detailed_definition": "one richer sentence",
 "example": "natural example sentence using the word",
 "easy_example": "very simple example sentence",
 "synonyms": ["w1","w2","w3"],
 "antonyms": ["w1","w2"],
 "related": ["w1","w2"],
 "confusing_words": [],
 "word_family": ["w1"],
 "roots": ["latin/greek root (meaning)"],
 "prefixes": [],
 "suffixes": [],
 "mnemonic": "short vivid memory hook",
 "common_mistakes": "one common confusion",
 "usage_notes": "short register/context note",
 "topic": "academic|everyday|business|science|emotions|society",
 "exam_relevance": ["ielts","toefl","gre","sat","gmat"],
 "frequency": 1-5,
 "academic_importance": 1-5
}"""


def parse_json_array(text: str) -> List[Dict]:
    """Parse a JSON array from AI response text."""
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return []


def validate_generated(w: Dict, level: str) -> bool:
    """Quick pre-validation before sending to the real pipeline."""
    if not isinstance(w, dict):
        return False
    hw = str(w.get("headword", "")).strip().lower()
    if not hw or not re.fullmatch(r"[a-z][a-z'-]{0,25}", hw):
        return False
    w["headword"] = hw
    if not (w.get("simple_definition") or "").strip():
        return False
    if not (w.get("example") or "").strip():
        return False
    # Force the intended CEFR level
    w["cefr"] = level
    # Sanitize topic
    if w.get("topic") not in TOPICS:
        w["topic"] = "everyday"
    # Sanitize exam_relevance
    w["exam_relevance"] = [e for e in (w.get("exam_relevance") or []) if e in EXAMS]
    # Sanitize arrays
    for arr in ["synonyms", "antonyms", "related", "confusing_words",
                "word_family", "roots", "prefixes", "suffixes"]:
        w[arr] = [str(x).strip() for x in (w.get(arr) or []) if str(x).strip()]
    # Sanitize numbers
    w["frequency"] = max(1, min(5, int(w.get("frequency") or 3)))
    w["academic_importance"] = max(1, min(5, int(w.get("academic_importance") or 3)))
    return True


async def generate_batch(
    words: List[str],
    level: str,
    existing: Set[str],
) -> List[Dict]:
    """Generate metadata for a batch of words using AI."""
    # Filter out words already existing
    targets = [w for w in words if normalize_headword(w) not in existing]
    if not targets:
        return []

    chat = LlmChat(
        api_key=KEY,
        session_id=f"expand-{level}-{hash(tuple(targets[:3]))}",
        system_message=(
            "You are a lexicographer creating accurate CEFR-aligned English vocabulary "
            "data for a learning app. Be factually correct. Never invent fake words. "
            "Every definition must be learner-friendly and accurate."
        ),
    ).with_model("openai", "gpt-5.6-luna")

    word_list = ", ".join(targets)
    prompt = (
        f"Generate vocabulary data for these {len(targets)} English words at CEFR {level}:\n"
        f"{word_list}\n\n"
        f"For each word, provide complete, accurate lexicographic data.\n"
        f"Assign appropriate topics from: academic, everyday, business, science, emotions, society\n"
        f"Assign exam relevance from: ielts, toefl, gre, sat, gmat (only if genuinely relevant)\n"
        f"Include real synonyms and antonyms where they exist.\n"
        f"Include confusing_words ONLY for genuinely confusable pairs.\n\n"
        f"{SCHEMA_PROMPT}"
    )

    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        print(f"    AI error for batch [{level}]: {e}")
        return []

    items = parse_json_array(resp if isinstance(resp, str) else str(resp))
    results = []
    for w in items:
        if validate_generated(w, level):
            key = normalize_headword(w["headword"])
            if key and key not in existing:
                existing.add(key)
                results.append(w)
    return results


async def run_expansion():
    """Main expansion workflow."""
    from db import get_db, reset_db_for_testing
    repo = get_db()

    print("=" * 70)
    print("VOCABIST CONTENT EXPANSION P1")
    print("=" * 70)

    # Load existing canonical keys
    all_words = await repo.load_all_words_minimal()
    existing_keys: Set[str] = set()
    for w in all_words:
        k = normalize_headword(w.get("headword", ""))
        if k:
            existing_keys.add(k)
    print(f"\nExisting words: {len(existing_keys)}")

    # Build the generation plan
    plan: List[Tuple[str, List[str]]] = []
    for level in LEVELS:
        candidates = WORD_LISTS.get(level, [])
        # Filter out already-existing words
        new_candidates = [
            w for w in candidates
            if normalize_headword(w) not in existing_keys
        ]
        if new_candidates:
            plan.append((level, new_candidates))
            print(f"  {level}: {len(new_candidates)} candidates (from {len(candidates)} total)")

    total_candidates = sum(len(ws) for _, ws in plan)
    print(f"\nTotal candidates to generate: {total_candidates}")

    # Generate and ingest in batches
    BATCH_SIZE = 15
    stats = {
        "generated": 0, "ingested_created": 0, "ingested_exists": 0,
        "ingested_rejected": 0, "generation_failed": 0, "batches": 0,
    }
    all_results = []

    for level, candidates in plan:
        print(f"\n--- Processing CEFR {level} ({len(candidates)} candidates) ---")

        for i in range(0, len(candidates), BATCH_SIZE):
            batch_words = candidates[i:i + BATCH_SIZE]
            stats["batches"] += 1
            print(f"  Batch {stats['batches']}: {batch_words[:3]}... ({len(batch_words)} words)")

            # Generate AI metadata
            generated = await generate_batch(batch_words, level, set(existing_keys))
            stats["generated"] += len(generated)

            if not generated:
                stats["generation_failed"] += len(batch_words)
                print(f"    -> 0 generated (AI returned no valid data)")
                continue

            # Ingest through the existing pipeline
            for w in generated:
                try:
                    outcome = await ingest_word(
                        repo, w, provenance="AI_GENERATED"
                    )
                    action = outcome.get("action", "unknown")
                    stats[f"ingested_{action}"] = stats.get(f"ingested_{action}", 0) + 1

                    if action == "created":
                        existing_keys.add(normalize_headword(w["headword"]))
                        all_results.append({
                            "headword": w["headword"],
                            "id": outcome.get("id"),
                            "status": outcome.get("status"),
                            "action": action,
                            "level": level,
                        })
                    elif action == "exists":
                        pass  # Already in corpus
                    elif action == "rejected":
                        errs = (outcome.get("validation") or {}).get("errors", [])
                        err_codes = [e.get("code") for e in errs[:3]]
                        print(f"    REJECTED {w['headword']}: {err_codes}")

                except Exception as e:
                    stats["generation_failed"] += 1
                    print(f"    INGEST ERROR {w.get('headword')}: {e}")

            created_in_batch = sum(1 for r in all_results[-len(generated):] if r.get("action") == "created")
            print(f"    -> {len(generated)} generated, {created_in_batch} created")

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

    # Add confusing_words relationships for words that exist
    print(f"\n--- Adding confusing_words relationships ---")
    confusion_updates = 0
    for w1, w2 in CONFUSING_PAIRS:
        k1, k2 = normalize_headword(w1), normalize_headword(w2)
        if k1 in existing_keys and k2 in existing_keys:
            # Load both words and update confusing_words
            word1 = await repo.get_word_by_headword(k1)
            word2 = await repo.get_word_by_headword(k2)
            if word1 and word2:
                # Update word1's confusing_words
                rels1 = word1.get("relations") or {}
                cw1 = rels1.get("confusing_words", [])
                if not any(normalize_headword(e.get("headword") if isinstance(e, dict) else e) == k2 for e in cw1):
                    cw1.append({"ref": word2["id"], "headword": k2})
                    rels1["confusing_words"] = cw1
                    await repo.update_word(word1["id"], {"relations": rels1})
                    confusion_updates += 1

                # Update word2's confusing_words
                rels2 = word2.get("relations") or {}
                cw2 = rels2.get("confusing_words", [])
                if not any(normalize_headword(e.get("headword") if isinstance(e, dict) else e) == k1 for e in cw2):
                    cw2.append({"ref": word1["id"], "headword": k1})
                    rels2["confusing_words"] = cw2
                    await repo.update_word(word2["id"], {"relations": rels2})
                    confusion_updates += 1

    print(f"  Confusing word updates: {confusion_updates}")

    # Run relationship resolution
    print(f"\n--- Running relationship resolution ---")
    from graph_service import resolve_all_relationship_refs
    resolve_stats = await resolve_all_relationship_refs(repo)
    print(f"  Resolution: {resolve_stats}")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"EXPANSION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Batches processed: {stats['batches']}")
    print(f"  Words generated by AI: {stats['generated']}")
    print(f"  Words created (new): {stats.get('ingested_created', 0)}")
    print(f"  Words already existed: {stats.get('ingested_exists', 0)}")
    print(f"  Words rejected: {stats.get('ingested_rejected', 0)}")
    print(f"  Generation failures: {stats['generation_failed']}")
    print(f"  Confusing word updates: {confusion_updates}")
    print(f"  Relationship resolution: {resolve_stats.get('updated', 0)} words updated")

    # Save results log
    log_path = os.path.join(_BACKEND_DIR, "expansion_results.json")
    with open(log_path, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "confusion_updates": confusion_updates,
            "resolve_stats": {k: v for k, v in resolve_stats.items()},
            "words_created": all_results,
        }, f, indent=2, default=str)
    print(f"\n  Results saved to: {log_path}")


if __name__ == "__main__":
    asyncio.run(run_expansion())
