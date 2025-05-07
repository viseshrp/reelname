import re
from re import Pattern

# Matches “Title (2023)”, “Title [2023]”, “Title {2023}” or “Title <2023>”
BRACKETED_PATTERN: Pattern[str] = re.compile(
    r"(?P<title>.+?)\s*[\(\[\{\<](?P<year>\d{4})[\)\]\}\>]"
)

# Matches “Title.2023.” style (e.g. for TV episodes/seasons)
DOT_YEAR_PATTERN: Pattern[str] = re.compile(r"^(?P<title>.+?)\.(?P<year>\d{4})\.")

# Matches “Title 2023 ” style (space-separated year, no brackets)
SPACE_YEAR_PATTERN: Pattern[str] = re.compile(r"^(?P<title>.+?)\s+(?P<year>\d{4})(?:\s|$)")
