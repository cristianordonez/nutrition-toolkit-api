# Nutrition Toolkit API

FastAPI interface for the nutrition toolkit application with CLI tool support.

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

- Make sure to include optional dependencies to start fastAPI server:

```bash
uv pip install -e ".[api]"
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

- Use docker compose to start postgresql and redis containers:

```bash
docker compose up -d
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

## Deployment

- Use the ntk-api command to run uvicorn on FastAPI app

```bash
uv run ntk-api
```

- containerize the REST API using Docker:

```bash
docker build -t ntk-api-image .
docker run -d --env database_host=host.docker.internal --add-host=host.docker.internal:host-gateway -p 3000:3000 --name ntk-api ntk-api-image
```

## Known Issues

- Due to issues with using Ty with pre-commit due to the tox-uv integration, the type checking tox command must be separated from the linting and formatting check command

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