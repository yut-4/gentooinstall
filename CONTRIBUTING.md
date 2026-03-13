# Contributing to gentooinstall

Contributions are welcome through pull requests and issues.

## Where to discuss changes

- Issues: https://github.com/gentooinstall/gentooinstall/issues
- Discord: https://discord.gg/aDeMffrxNg

## Branching

- `master` is the main development branch.
- Stable releases are represented by tags.
- Patch work for a release should target a dedicated release branch.

## Coding conventions

Project style is close to PEP 8 with project-specific rules:

- Tabs are used for indentation.
- Maximum line length is enforced by lint configuration.
- Use Unix line endings.
- Follow existing quote style and formatting in each file.

## Local checks

Install and enable pre-commit hooks:

```sh
pre-commit install
```

Run checks manually when needed:

```sh
pre-commit run --all-files
```

## Documentation

To build docs locally, see [`docs/README.md`](docs/README.md).

## Pull requests

- Explain why the change is needed.
- Include tests when behavior changes.
- Keep commits readable and avoid rewriting history during review.

## Maintainer

- Anton Hvornum ([@Torxed](https://github.com/Torxed))

Contributors graph:
- https://github.com/gentooinstall/gentooinstall/graphs/contributors
