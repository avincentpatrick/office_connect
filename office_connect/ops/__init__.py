"""Operations tooling — backup, restore drill, deploy guard (Increment 2).

Cross-platform Python that runs INSIDE the app/worker container (identical on
Windows dev and the production Ubuntu VM). Imports ``core`` freely; import-linter
only constrains ``core`` <-> ``modules``, so this package keeps ``lint-imports``
green. The Celery task (``ops.tasks``) and the manual CLI (``python -m
office_connect.ops``) call the same functions — one source of truth.
"""
