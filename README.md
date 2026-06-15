# python-template

Template repository for creating extendable and modern python cli and gui applications. Well documented configuration files so it can be edited to match projects needs.

## TODO

- generate command line options using pydantic models

- add config.ini support for command line options

- update AUTHORS file

- add config.ini support for arguments

- run and configure test suite for python 3.12, 3.13, and 3.14

- set up ty type checking and ruff using pre commit

- set up sphinx documentation

- set up pre commit

- change versioning to use semantic versioning instead of date

- containerize with docker

- add option to run jobs/commands in parallel use a parallel runner class that can change between using threads and processes

- set up github actions - lint, format, type check, build, test, deploy package to github packages


- create workflow to update version in __version__.py, consider using uv or hatch to release new version

- add branch protection rules on repository

- Update README.md

- For practice app, create mcp server that pulls in official academy of nutrition and dietetics textbooks for context

# Development

- System python is available at /usr/bin/python3

- Python shim created using pyenv is available at ~/.pyenv/shims. View all available shims with following command:

```bash
pyenv versions
```

- Virtual environments are managed with uv. Install new python versions with the following command:

```bash
uv python install <version>
```

- View all available uv managed python versions with the following command:

```bash
uv python list
```

- Install package locally

```bash
uv pip install -e .
```

- Update uv.lock

```bash
uv sync
```

- Run application

```bash
uv run python -m python_template
```

- To add packages to repository, use following command from the root of the repository:

```bash
uv add pydantic
```

# Pre-Commit

- Install pre-commit with uv

```bash
uv tool install pre-commit
```

- Install git-hooks scripts

```bash
pre-commit install
```

# Testing

- Install tox with uv

```bash
uv tool install tox --with tox-uv
```

# References

[uv](https://docs.astral.sh/uv/concepts/tools/#tool-versions)
[tox-uv](https://github.com/tox-dev/tox-uv)
[ruff](https://docs.astral.sh/ruff/)
[ty](https://docs.astral.sh/ty/)

- [Customization](https://code.visualstudio.com/docs/copilot/concepts/customization)
- [mcp-server](https://modelcontextprotocol.io/extensions/apps/build#manual-setup)
