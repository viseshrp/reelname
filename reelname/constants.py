from datetime import timedelta
import re
from re import Pattern

# Matches a year wrapped in brackets, a strong hint that it is the release year:
#   "Title (2023)", "Title [2023]", "Title {2023}", "Title <2023>"
# Regex breakdown:
#   [\(\[\{\<]            → Match any opening bracket: (, [, {, or <
#   (?P<year>\d{4})       → Named group "year": exactly 4 digits
#   [\)\]\}\>]            → Match any closing bracket: ), ], }, or >
BRACKETED_YEAR_PATTERN: Pattern[str] = re.compile(r"[\(\[\{\<](?P<year>\d{4})[\)\]\}\>]")

# Matches a 4-digit number standing on its own, a possible release year:
#   "Title.2023.1080p", "Title 2023 x264", "Title_2023"
# but not digits inside a token, like "1080p", "x2640" or "EDGE2020".
# Regex breakdown:
#   (?<![A-Za-z0-9])      → Not preceded by a letter or digit
#   (?P<year>\d{4})       → Named group "year": exactly 4 digits
#   (?![A-Za-z0-9])       → Not followed by a letter or digit
YEAR_TOKEN_PATTERN: Pattern[str] = re.compile(r"(?<![A-Za-z0-9])(?P<year>\d{4})(?![A-Za-z0-9])")

# Release years outside this range are numbers that only look like years ("1080", "2049").
EARLIEST_YEAR = 1888  # the oldest surviving film

# Matches a TV episode marker, where the show name ends:
#   "S01E07", "s01.e07", "S01E07E08", "1x07"
# but not resolutions like "1920x1080".
# Regex breakdown:
#   (?<![A-Za-z0-9])                      → Not preceded by a letter or digit
#   [Ss](?P<season>\d{1,2})[ ._-]?        → "S" + 1-2 digit season, optional separator
#   [Ee](?P<episode>\d{1,3})              → "E" + 1-3 digit episode
#   |                                     → OR
#   (?P<x_season>\d{1,2})x(?P<x_episode>\d{2,3})  → "1x07" style
#   (?!\d)                                → Not followed by another digit
EPISODE_PATTERN: Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9])(?:[Ss](?P<season>\d{1,2})[ ._-]?[Ee](?P<episode>\d{1,3})"
    r"|(?P<x_season>\d{1,2})x(?P<x_episode>\d{2,3}))(?!\d)"
)

# Matches release info that marks where a title without a year ends:
#   "Dune.Part.Two.1080p.WEB-DL", "Some Title x264", "Some.Title.REMASTERED.BluRay"
# Technical tokens match in any case. Edition tokens must be upper case, so titles
# like "Uncut Gems" keep their words. Words that are also common in titles ("Web",
# "Cam", "TS") are deliberately left out.
# Regex breakdown:
#   (?<![A-Za-z0-9])      → Not preceded by a letter or digit
#   (?i:...)              → Case-insensitive: resolution, source, codec, audio tokens
#   |REMASTERED|...       → Case-sensitive upper-case edition tokens
#   (?![A-Za-z0-9])       → Not followed by a letter or digit
RELEASE_INFO_PATTERN: Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"(?i:\d{3,4}[pi]|4k|uhd|hdr(?:10)?|10bit"
    r"|blu-?ray|bdrip|brrip|web-?dl|web-?rip|hdtv|hdrip|dvdrip|dvdscr"
    r"|[xh]\.?26[45]|hevc|xvid|divx|av1"
    r"|aac(?:\d\.\d)?|ac3|dts(?:-hd)?|ddp?\d\.\d|truehd|atmos"
    r"|directors?.cut|extended.cut|theatrical.cut)"
    r"|REMASTERED|EXTENDED|UNRATED|UNCUT|PROPER|REPACK|IMAX|LIMITED|INTERNAL"
    r")(?![A-Za-z0-9])"
)

# Matches characters that are not allowed in Windows filenames:
#   < > : " / \ | ? *
# Regex breakdown:
#   [<>:"/\\|?*]           → Match any one of these characters literally
#   Double escaping \\     → Needed for backslash inside regex string
#   strip spaces and . at the end
INVALID_FILENAME_CHARS: Pattern[str] = re.compile(r'[<>:"/\\|?*]|[ .]+$')

# Matches tracker prefixes at the beginning of filenames like:
#   "www.1TamilMV.fi - ", "yts.mx - ", "1337x.to - "
# Regex breakdown:
#   ^                            → Anchor to start of string
#   (?:                          → Non-capturing group:
#       www\.[\w.-]+             → Starts with "www." followed by domain characters
#       (letters, digits, dash, dot)
#       |                        → OR
#       \w+\.\w{2,}              → Domain name like "yts.mx" or "1337x.to"
#   )
#   (?:\s*[--]\s*)               → Optional spaces, then dash or en dash (two hyphens),
#   then optional spaces
URL_PREFIX_PATTERN: Pattern[str] = re.compile(
    r"^(?:www\.[\w.-]+|\w+\.\w{2,})(?:\s*[--]\s*)", re.IGNORECASE
)

# Matches a release group prefix like "LOL. " in "LOL. The.Mentalist.S04E16.HDTV-LOL".
# It is only stripped when the name also ends with the same group ("-LOL").
# Regex breakdown:
#   ^(?P<group>[A-Za-z0-9]+)     → Group name at the very start
#   \.\s+                        → A dot followed by whitespace
GROUP_PREFIX_PATTERN: Pattern[str] = re.compile(r"^(?P<group>[A-Za-z0-9]+)\.\s+")

# Matches sample and trailer clips (checked against the name without its extension) like:
#   "Movie.2010.1080p-sample", "sample-movie.2010", "Movie (2010) [Trailer]"
# but not titles that merely contain the word, like "Trailer.Park.Boys.2006".
# Regex breakdown:
#   (?:^|[\W_])            → Start of name, or a separator before the word
#   (?:sample|trailer)     → The word "sample" or "trailer"
#   (?:$|[-\)\]\}])        → End of name, a dash, or a closing bracket after the word
SAMPLE_PATTERN: Pattern[str] = re.compile(
    r"(?:^|[\W_])(?:sample|trailer)(?:$|[-\)\]\}])", re.IGNORECASE
)

# Extensions of files reelname renames: videos, and the subtitles that sit next to them.
VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {".3gp", ".avi", ".divx", ".flv", ".m2ts", ".m4v", ".mk3d", ".mkv", ".mov"}
    | {".mp4", ".mpeg", ".mpg", ".ogm", ".rmvb", ".ts", ".vob", ".webm", ".wmv"}
)
SUBTITLE_EXTENSIONS: frozenset[str] = frozenset(
    {".ass", ".idx", ".smi", ".srt", ".ssa", ".sub", ".sup", ".vtt"}
)
MEDIA_EXTENSIONS: frozenset[str] = VIDEO_EXTENSIONS | SUBTITLE_EXTENSIONS
# Files renamed along with a video whose name they start with ("Movie.en.srt", "Movie.nfo").
SIDECAR_EXTENSIONS: frozenset[str] = SUBTITLE_EXTENSIONS | {".nfo"}

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/{kind}"

# Minimum match scores: a year in the filename confirms a candidate, so it can be fuzzier.
MATCH_SCORE_WITH_YEAR = 80.0
MATCH_SCORE_WITHOUT_YEAR = 90.0

# How long cached TMDb searches stay fresh. Empty results expire sooner, so newly
# added titles are found again.
CACHE_TTL_HIT = timedelta(days=7)
CACHE_TTL_MISS = timedelta(days=1)

# In watch mode, wait this long after the last change before renaming, so files still
# being copied or downloaded are left alone.
WATCH_SETTLE_SECONDS = 2.0
