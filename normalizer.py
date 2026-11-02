"""
normalizer.py - Acoustic and Phonetic Normalization Engine for SIT Humanoid Robot.

Cleans Vosk speech-to-text outputs and handles regional Indian accents,
mapping mistranscriptions into canonical keywords while preserving question syntax.
"""

import re

# Precise acoustic and speech mistranscription replacements
PHONETIC_REPLACEMENTS = [
    # College identity & name distortions
    (r"\b(s\s*i\s*t|s\.i\.t|safety|s\s*it|say\s*it|see\s*it|sayt|es\s*eye\s*tee)\b", "sit"),
    (r"\b(siddaganga|sidaganga|siddiganga|sidganga|siddagange|siddhaganga|sree\s*siddaganga|shree\s*siddaganga|shri\s*siddaganga)\b", "siddaganga"),
    (r"\b(tumkur|tumakuru|toomkoor|toomecoor|tom\s*cur|tumm\s*kur|thumkur)\b", "tumakuru"),
    (r"\b(v\s*t\s*u|vtu|vishweshwaraya|visvesvaraya|visveswaraya)\b", "vtu"),
    (r"\b(a\s*i\s*c\s*t\s*e|aicte)\b", "aicte"),
    (r"\b(n\s*a\s*a\s*c|naac)\b", "naac"),
    (r"\b(n\s*b\s*a|nba)\b", "nba"),
    (r"\b(n\s*i\s*r\s*f|nirf)\b", "nirf"),

    # Key Personnel & Leadership
    (r"\b(principle|principles|prince\s*bull|prince\s*pull|prince\s*pal)\b", "principal"),
    # Common Whisper renderings from the supplied mic run.
    (r"\b(principal|principle) of a set\b", "principal of sit"),
    (r"\b(principal|principle) of sad\b", "principal of sit"),
    (r"\b(dinesh|the\s*nesh|denish|the\s*nash|dinesha)\b", "dinesh"),
    (r"\b(shivakumara|sivakumara|shiva\s*kumara|siva\s*kumara|shivakumar)\b", "shivakumara"),
    (r"\b(swamiji|swamyji|swami|swamy|swamigalu|walking\s*god|trividha\s*dasohi)\b", "swamiji"),
    (r"\b(siddalinga|siddalingaswamy|siddalinga\s*swamiji|sidhalinga)\b", "siddalinga"),
    (r"\b(channabasappa|chennabasappa|chana\s*basava|chan\s*basapa|chennabasappa)\b", "channabasappa"),
    (r"\b(shivakumaraiah|shiva\s*kumar\s*aya|shivakumarayya)\b", "shivakumaraiah"),
    (r"\b(c\s*e\s*o|ceo)\b", "ceo"),
    (r"\b(h\s*o\s*d|hod|head\s*of\s*department)\b", "hod"),

    # Departments & Engineering Branches
    (r"\b(c\s*s\s*e|cs\s*branch|cs\s*dept|comp\s*sci|computer\s*science)\b", "cse"),
    (r"\b(i\s*s\s*e|is\s*branch|is\s*dept|info\s*sci|information\s*science)\b", "ise"),
    (r"\b(a\s*i\s*m\s*l|aiml|ai\s*ml|artificial\s*intelligence)\b", "aiml"),
    (r"\b(a\s*i\s*d\s*s|aids|ai\s*ds|data\s*science)\b", "aids"),
    (r"\b(e\s*c\s*e|ec\s*branch|ec\s*dept|electronics\s*and\s*communication)\b", "ece"),
    (r"\b(e\s*e\s*e|triple\s*e|ee\s*branch|ee\s*dept|electrical\s*and\s*electronics)\b", "eee"),
    (r"\b(e\s*t\s*e|telecom|telecommunication|electronics\s*and\s*telecommunication)\b", "ete"),
    (r"\b(mech\s*branch|mech\s*dept|mech|mechanical|mechanical\s*engineering)\b", "mechanical"),
    (r"\b(civil\s*branch|civil\s*dept|civil|civil\s*engineering)\b", "civil"),
    (r"\b(biotech|bio\s*tech|bt\s*branch|bt\s*dept|biotechnology)\b", "biotechnology"),
    (r"\b(chem\s*eng|chemical\s*eng|chemical\s*engineering)\b", "chemical"),
    (r"\b(i\s*e\s*m|iem|industrial\s*engineering)\b", "iem"),
    (r"\b(b\s*arch|barch|architecture\s*department)\b", "architecture"),
    (r"\b(m\s*b\s*a|mba|business\s*administration)\b", "mba"),
    (r"\b(m\s*c\s*a|mca|computer\s*applications)\b", "mca"),

    # Admissions, Exams & Fees
    (r"\b(k\s*c\s*e\s*t|kcet|k-cet|k\s*cet|case\s*at|k\s*set)\b", "kcet"),
    (r"\b(comed\s*k|comedk|comed-k)\b", "comedk"),
    (r"\b(cut\s*off|cutoff|closing\s*rank)\b", "cutoff"),
    (r"\b(fee|fees|fee\s*structure|tuition\s*fees)\b", "fees"),
    (r"\b(cie|internal|internals|internal\s*marks|internal\s*test)\b", "cie"),
    (r"\b(s\s*e\s*e|see\s*exam|see\s*exams|externals|semester\s*end\s*exam|sem\s*exam|end\s*exam)\b", "see exam"),
    (r"\b(sgpa|cgpa|gpa)\b", "cgpa"),
    (r"\b(c\s*o\s*e|coe|controller\s*of\s*examinations)\b", "coe"),

    # Placements & Salaries
    (r"\b(highest\s*package|highest\s*salary|top\s*package|max\s*package|highest\s*placement)\b", "highest package"),
    (r"\b(average\s*package|average\s*salary|avg\s*package|median\s*package)\b", "average package"),
    (r"\b(salary|salaries|lpa|ctc)\b", "salary package"),
    (r"\b(placements?|campus\s*drive|recruiter|recruiters|job\s*offers?)\b", "placement"),

    # Facilities & Infrastructure
    (r"\b(hostal|hostels?|accommodation)\b", "hostel"),
    (r"\b(boys?\s*hostel|gents\s*hostel)\b", "boys hostel"),
    (r"\b(girls?\s*hostel|ladies\s*hostel)\b", "girls hostel"),
    (r"\b(canteen|kanteen|cafeteria|hotel|food\s*court)\b", "canteen"),
    (r"\b(lib|library|books|reference\s*section|digital\s*library|reading\s*room)\b", "library"),
    (r"\b(audi|auditorium|birla|bella|birla\s*audi|birla\s*auditorium)\b", "birla auditorium"),
    (r"\b(gandhi\s*bhavan|gandhi\s*hall)\b", "gandhi bhavan"),
    (r"\b(doctor|medical|clinic|dispensary|hospital|first\s*aid|ambulance|sick)\b", "health centre"),
    (r"\b(canara\s*bank|atm)\b", "bank atm"),
    (r"\b(sports?|playground|gym|gymnasium|badminton|cricket\s*ground)\b", "sports"),

    # Events & Festivals
    (r"\b(halcyon|hall\s*sean|helsian|halsion)\b", "halcyon"),
    (r"\b(expo|sit\s*expo)\b", "sit expo"),
    (r"\b(robocore|robotics\s*club)\b", "robocore")
]


def normalize_query(text: str) -> str:
    """
    Normalizes input text for offline voice interaction:
    - Lowercases
    - Strips unwanted punctuation
    - Applies phonetic regex rules
    - Collapses whitespace
    """
    if not text:
        return ""

    q = text.lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)

    for pattern, replacement in PHONETIC_REPLACEMENTS:
        q = re.sub(pattern, replacement, q)

    return " ".join(q.split())
