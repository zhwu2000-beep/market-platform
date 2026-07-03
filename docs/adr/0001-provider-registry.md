# ADR 0001: Provider Registry

## Status
Accepted

## Context
- The project will support multiple market data providers.
- Upper layers should not depend on concrete provider classes.
- Providers should support lazy configuration validation.

## Decision
- Introduce a `ProviderRegistry`.
- Use a lightweight class-based registry.
- Provide a default `get_provider(name, **kwargs)` convenience function later.
- Keep provider construction lazy and dependency-injection friendly.

## Consequences
- Upper layers can depend on the `DataProvider` interface.
- Adding new providers becomes easier.
- Tests can inject fake providers.
- The registry should remain small and not become a service container.
