import re
from re import Pattern

# Matches “Title (2023)” with any bracket type
BRACKETED_PATTERN: Pattern[str] = re.compile(r"(?P<title>.+?)\s*[\(\[\{<](?P<year>\d{4})[\)\]\}>]")

# Matches “Title.2023.” style (e.g. for TV episodes/seasons)
DOT_YEAR_PATTERN: Pattern[str] = re.compile(r"^(?P<title>.+?)\.(?P<year>\d{4})\.")
