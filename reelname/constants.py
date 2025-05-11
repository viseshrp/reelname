import re
from re import Pattern

# Matches titles with a bracketed year like:
#   "Title (2023)", "Title [2023]", "Title {2023}", "Title <2023>"
# Regex breakdown:
#   (?P<title>.+?)        → Named group "title": matches any character (non-greedy)
#   \s*                   → Optional whitespace between title and year
#   [\(\[\{\<]            → Match any opening bracket: (, [, {, or <
#   (?P<year>\d{4})       → Named group "year": exactly 4 digits
#   [\)\]\}\>]            → Match any closing bracket: ), ], }, or >
BRACKETED_PATTERN: Pattern[str] = re.compile(
    r"(?P<title>.+?)\s*[\(\[\{\<](?P<year>\d{4})[\)\]\}\>]"
)

# Matches titles with a dot-year-dot pattern:
#   "Title.2023." or "Some.Show.2010."
# Regex breakdown:
#   ^                    → Anchor to start of string
#   (?P<title>.+?)       → Named group "title": any characters (non-greedy), up to the year
#   \.                   → Literal dot before the year
#   (?P<year>\d{4})      → Named group "year": exactly 4 digits
#   \.                   → Literal dot after the year
DOT_YEAR_PATTERN: Pattern[str] = re.compile(r"^(?P<title>.+?)\.(?P<year>\d{4})\.")

# Matches titles with space-separated year:
#   "Title 2023" or "Title 2023 Something"
# Regex breakdown:
#   ^                      → Anchor to start of string
#   (?P<title>.+?)         → Named group "title": any characters (non-greedy), up to year
#   \s+                    → One or more spaces
#   (?P<year>\d{4})        → Named group "year": exactly 4 digits
#   (?:\s|$)               → Non-capturing group: either a space or end of string
SPACE_YEAR_PATTERN: Pattern[str] = re.compile(r"^(?P<title>.+?)\s+(?P<year>\d{4})(?:\s|$)")

# Matches characters that are not allowed in Windows filenames:
#   < > : " / \ | ? *
# Regex breakdown:
#   [<>:"/\\|?*]           → Match any one of these characters literally
#   Double escaping \\     → Needed for backslash inside regex string
INVALID_FILENAME_CHARS: Pattern[str] = re.compile(r'[<>:"/\\|?*]')

# Matches tracker prefixes at the beginning of filenames like:
#   "www.1TamilMV.fi - ", "yts.mx - ", "1337x.to - "
# Regex breakdown:
#   ^                            → Anchor to start of string
#   (?:                          → Non-capturing group:
#       www\.[\w.-]+             → Starts with "www." followed by domain characters (letters, digits, dash, dot)
#       |                        → OR
#       \w+\.\w{2,}              → Domain name like "yts.mx" or "1337x.to"
#   )
#   (?:\s*[--]\s*)               → Optional spaces, then dash or en dash (two hyphens), then optional spaces
URL_PREFIX_PATTERN: Pattern[str] = re.compile(
    r"^(?:www\.[\w.-]+|\w+\.\w{2,})(?:\s*[--]\s*)", re.IGNORECASE
)
