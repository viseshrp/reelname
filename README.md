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

* To view the help message, run the following command:

```bash
reelname --help
```

## 🛠️ Features

* Fixes media filenames with random characters.
* Only renames video and subtitle files, and skips samples and trailers.
* Leaves a file alone when TMDb doesn't confirm its title and year.
* Never overwrites an existing file.

## 🧾 Changelog

See [CHANGELOG.md](https://github.com/viseshrp/reelname/blob/main/CHANGELOG.md)

## 🙏 Credits

* [Click](https://click.palletsprojects.com), for enabling delightful CLI development.
* [TMDb](https://www.themoviedb.org/), for movie data. This product uses the
  TMDB API but is not endorsed or certified by TMDB.
* Inspired by [Simon Willison](https://github.com/simonw)'s work.

## 📄 License

MIT © [Visesh Prasad](https://github.com/viseshrp)
