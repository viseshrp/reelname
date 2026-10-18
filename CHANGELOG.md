# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- TV episodes: names with `S01E07` or `1x07` are looked up as TV shows and
  renamed to `Show (Year) S01E07 …`.
- Names without a year (`Dune.Part.Two.1080p.mkv`) are looked up too, and
  skipped when more than one title fits.
- Subtitles and `.nfo` files are renamed together with their video.
- `--dry-run` shows what would be renamed without renaming anything.
- Every rename is logged, and `--undo` renames the last run's files back.
- TMDb searches are cached on disk for a week (a day when nothing was found).
- Opt-in live TMDb tests: set `REELNAME_LIVE_TMDB_API_KEY` and run
  `pytest -m integration`.

### Changed

- Colons in titles become ` - ` instead of being dropped.
- Watch mode waits for files to stop changing before renaming them.
- A leading release group (`LOL. Show.S01E01…-LOL`) is dropped from the name.

### Fixed

- Numbers that only look like years (`1080`, `2049` in
  `Blade.Runner.2049.2017`) are no longer taken as the release year.

## [3.0.0] - 2026-10-18

### Changed

- **Breaking:** look up titles on TMDb instead of IMDb. IMDb now blocks
  Cinemagoer, so lookups had stopped working. Set `TMDB_API_KEY` to a TMDb API
  key or read access token.
- Files with no confirmed TMDb match are skipped instead of renamed from the
  filename alone.
- Only video and subtitle files are renamed; samples and trailers are skipped.

### Fixed

- Renaming could overwrite an existing file when two files cleaned up to the
  same name.
- The extension was lost when the year came right before it (`Movie.2010.mkv`).
- Title matching was case-sensitive.
- Crash on Python 3.14 (no current event loop).

## [2.0.4] - 2025-06-13

### Fixed

- IMDb search and matching

## [2.0.3] - 2025-05-13

### Fixed

- Extraction

## [2.0.2] - 2025-05-13

### Added

- support for more patterns

## [2.0.1] - 2025-05-11

### Added

- support for more patterns

## [2.0.0] - 2025-05-11

### Added

- use imdb and fuzzy match for intelligent matching
- add --watch to make continuous watching optional
- support for more patterns

## [1.0.0] - 2025-05-04

### Added

- First release
- Ability to run fixer on a list of files in a directory
- Auto run when changes are detected in the directory

## [0.0.1] - 2025-04-30

### Added

- Stub release
