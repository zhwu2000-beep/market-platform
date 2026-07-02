"""Run local development checks."""

from __future__ import annotations

import subprocess


def main() -> None:
    """Run the standard local checks."""

    commands = [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", "src"],
        ["uv", "run", "pytest"],
    ]
    for command in commands:
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
