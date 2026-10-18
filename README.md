# reelname

[![PyPI version](https://img.shields.io/pypi/v/reelname.svg)](https://pypi.org/project/reelname/)
[![Python versions](https://img.shields.io/pypi/pyversions/reelname.svg?logo=python&logoColor=white)](https://pypi.org/project/reelname/)
[![CI](https://github.com/viseshrp/reelname/actions/workflows/main.yml/badge.svg)](https://github.com/viseshrp/reelname/actions/workflows/main.yml)

[![License: MIT](https://img.shields.io/github/license/viseshrp/reelname)](https://github.com/viseshrp/reelname/blob/main/LICENSE)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/en/stable/)
[![Lint: Ruff](https://img.shields.io/badge/lint-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![Typing: mypy](https://img.shields.io/badge/typing-checked-blue.svg)](https://mypy.readthedocs.io/en/stable/)

> A tool to fix media file names

![Demo](https://raw.githubusercontent.com/viseshrp/reelname/main/demo.gif)

## 📐 Requirements

* Python >= 3.9

## 📦 Installation

```bash
pip install reelname
```

## 🧪 Usage

* reelname looks up titles on [TMDb](https://www.themoviedb.org/), so it
  needs a free TMDb API key or API read access token from
  <https://www.themoviedb.org/settings/api>. Export it before running reelname:

```bash
export TMDB_API_KEY=your-key-or-token
```

* Preview the renames first, then run them:

```bash
reelname --dry-run /path/to/media
reelname /path/to/media
```

* Sort a downloads folder (and its subfolders) into a library without
  breaking seeding torrents: the library gets hardlinks with the new names,
  and the downloads stay as they are:

```bash
reelname -r --hardlink -o /path/to/library /path/to/downloads
```

* Name episodes the way Plex and Jellyfin like them, with their titles
  (`Breaking Bad (2008) - S01E01 - Pilot.mkv`):

```bash
reelname --episode-titles /path/to/shows
```

* Changed your mind? Undo the last run in that folder:

```bash
reelname --undo /path/to/media
```

* To view the help message, run the following command:

```bash
reelname --help
```

## 🛠️ Features

* Renames movies to `Title (Year) …` and TV episodes to `Show (Year) S01E07 …`,
  keeping the release info that follows.
* Finds the title even without a year (`Dune.Part.Two.1080p.mkv`), and tells
  real years from numbers in titles (`Blade.Runner.2049.2017`).
* Uses more than the file name when it has to: an IMDb ID in the name or in an
  `.nfo` file (a movie's, a show's or an episode's), the release folder
  (`Inception.2010.1080p-GRP/abc123.mkv`), or the show folder
  (`Breaking Bad/Season 1/S01E01.mkv`, even `Breaking Bad/Season 2/05.mkv`).
* Matches original and alternative titles (`Gisaengchung` → `Parasite`),
  ignores accents (`Amelie` → `Amélie`), and finds long titles from their start
  (`Birdman` → `Birdman or (The Unexpected Virtue of Ignorance)`).
* Renames subtitles and `.nfo` files together with their video.
* Turns colons into dashes (`Mission - Impossible`) and slashes into spaces
  (`Face Off`) instead of dropping them.
* Only renames video and subtitle files, and skips samples and trailers.
* Leaves a file alone when TMDb doesn't confirm it, or when the name could be
  more than one title (like a remake).
* Never overwrites an existing file.
* Renames a Blu-ray or DVD folder as a whole (`Heat (1995) BluRay`), and never
  anything inside it.
* Says when a name is taken by an identical file (`duplicate of …`).
* Caches TMDb answers, revalidates them cheaply when they expire, falls back
  to them when TMDb is unreachable, retries when TMDb is busy, and in watch
  mode waits for files and folders to finish copying.
* Logs every rename, so `--undo` can put names back.

Searches are cached in `~/.cache/reelname` and the rename history is kept in
`~/.local/share/reelname` (or under `$XDG_CACHE_HOME` and `$XDG_DATA_HOME`).
Set `REELNAME_CACHE_DIR` or `REELNAME_DATA_DIR` to use other folders.

## 🧾 Changelog

See [CHANGELOG.md](https://github.com/viseshrp/reelname/blob/main/CHANGELOG.md)

## 🙏 Credits

* [Click](https://click.palletsprojects.com), for enabling delightful CLI development.
* [TMDb](https://www.themoviedb.org/), for movie data. This product uses the
  TMDB API but is not endorsed or certified by TMDB.
* Inspired by [Simon Willison](https://github.com/simonw)'s work.

## 📄 License

MIT © [Visesh Prasad](https://github.com/viseshrp)
