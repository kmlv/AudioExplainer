# Contributing

Thanks for helping improve AudioExplainer.

## Development setup

Install the project and development dependencies with `uv`:

```bash
uv sync --extra dev
```

Run the local checks before submitting a change:

```bash
uv run pytest
uv build
git diff --check
```

Tests must not require network access or a locally installed speech provider.
Mock provider behavior when testing synthesis paths.

## Pull requests

- Keep each change focused and explain its user-visible effect.
- Add or update tests for behavior changes.
- Do not commit generated audio, delivery artifacts, credentials, private text,
  local paths, or internal agent/session data.
- Keep accessibility and keyboard behavior intact when changing the player.
- Note any licensing implications when adding a provider, model, or dependency.

By contributing, you agree that your contribution is licensed under the MIT
License that covers this repository.
