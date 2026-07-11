# Nutrition Toolkit API

FastAPI interface for the nutrition toolkit application with CLI tool support.

## TODO

- run and configure test suite for python 3.12, 3.13, and 3.14

- set up ty type checking and ruff using pre commit

- set up sphinx documentation

- set up pre commit

- change versioning to use semantic versioning instead of date

- containerize with docker

- add option to run jobs/commands in parallel use a parallel runner class that can change between using threads and processes

- set up github actions - lint, format, type check, build, test, deploy package to github packages

- create workflow to update version in __version__.py, consider using uv or hatch to release new version

- publish to pypi

- add branch protection rules on repository

- Update README.md

## Development

- System python is available at /usr/bin/python3

- Python shim created using pyenv is available at ~/.pyenv/shims. View all available shims with following command:

```bash
pyenv versions
```

- Virtual environments are managed with uv. Create new virtual environment and install new python versions with the following command:

```bash
uv venv
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
uv run ntk
```

- To add packages to repository, use following command from the root of the repository:

```bash
uv add pydantic
```

## Pre-Commit

- Install pre-commit with uv

```bash
uv tool install pre-commit --with pre-commit-uv
```

- Install git-hooks scripts

```bash
pre-commit install
```

## Testing

- Install tox with uv

```bash
uv tool install tox --with tox-uv
```

- Using the tox command will run all pre-commit hooks which include linting, formatting and type checking the code base. To run a single pre commit hook use the following command:

```bash
pre-commit run <hook-id>
```

## References

- [Customizaition][customization]
- [MCP Server][mcp-server]
- [Documentation with Readthedocs][readthedocs]
- [uv][uv]
- [Using Tox with UV][tox-uv]
- [Ruff integration][ruff]
- [Ty type checking][ty]
- [Sphinx][sphinx-rtd]

[customization]: https://code.visualstudio.com/docs/copilot/concepts/customization
[mcp-server]: https://modelcontextprotocol.io/extensions/apps/build#manual-setup
[readthedocs]: https://app.readthedocs.org/projects/nutrition-toolkit-api/
[uv]: https://docs.astral.sh/uv/concepts/tools/#tool-versions
[tox-uv]: https://github.com/tox-dev/tox-uv
[ruff]: https://docs.astral.sh/ruff/
[sphinx-rtd]: https://sphinx-rtd-tutorial.readthedocs.io/en/latest/sphinx-config.html
[ty]: https://docs.astral.sh/ty/