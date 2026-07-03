# AGENTS.md

## Project Architecture Principles
- Keep boundaries explicit and narrow.
- Prefer small, composable layers over shared catch-all modules.
- Use lazy validation for provider configuration.
- Prefer dependency injection for HTTP clients and other external integrations.

## Coding Conventions
- Use snake_case for Python modules and functions.
- Use PascalCase for classes.
- Use UPPER_CASE for constants.
- Keep changes small and focused.
- Do not modify unrelated files.

## Documentation Conventions
- Documentation files use `snake_case.md`.
- Keep documentation practical and concise.
- Do not add documentation unless it is needed for the task.

## Git Workflow
- Use one feature per branch and one feature per pull request.
- Keep the git diff as small as possible.
- Avoid unrelated cleanup while working on a task.

## Commit Message Conventions
- Use short, imperative commit messages.
- State the user-visible intent of the change.
- Keep one logical change per commit.

## Testing Requirements
- Run `pytest`, `ruff`, and `mypy` locally before committing.
- Add or update tests for behavior changes.
- Prefer mocked tests for provider and HTTP boundary work unless a real integration test is explicitly requested.

## Review Workflow
- Review the diff before merging.
- Confirm the change matches the requested scope.
- Check for test coverage gaps and accidental scope creep.

## Notes for Codex and AI Agents
- Follow the requested scope exactly.
- Do not over-engineer or pre-split files.
- Provider configuration should validate lazily.
- Keep provider HTTP access behind injected clients.
- If `git push` fails with GitHub HTTPS connection errors, try switching VPN/proxy mode to `Direct` before changing git configuration.
