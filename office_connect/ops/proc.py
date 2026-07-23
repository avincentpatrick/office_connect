"""Thin subprocess wrapper for the Postgres CLI tools.

Runs a command with an explicit environment, captures output, and raises a
``RuntimeError`` carrying stderr on any non-zero exit — so every failure in the
backup / restore drill surfaces loudly (never a silent false-green).
"""

import subprocess


class CommandError(RuntimeError):
    """A subprocess exited non-zero; message carries argv + captured stderr."""


def run(cmd: list[str], *, env: dict[str, str], what: str) -> str:
    """Run ``cmd`` to completion. Return stdout; raise ``CommandError`` on failure.

    ``env`` fully replaces the child environment (build it via
    ``dsn.libpq_env`` so PGPASSWORD is present and no secret hits argv).
    """
    result = subprocess.run(  # noqa: S603 - fixed argv from our own callers
        cmd,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CommandError(
            f"{what} failed (exit {result.returncode}): "
            f"{' '.join(cmd[:1])} ... :: {result.stderr.strip()}"
        )
    return result.stdout
