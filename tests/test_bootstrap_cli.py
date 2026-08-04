"""QA gate: bootstrap CLI (Increment 3).

The DB subcommands are exercised through their async helpers (calling
``main()`` for those would nest ``asyncio.run`` inside the test loop). The
sync branches — production refusal and ``send-test-email`` — go through
``main()`` directly.
"""

import json

from sqlalchemy import select

from office_connect.core.config import Settings, get_settings
from office_connect.core.models import Activity, TenantConfig
from office_connect.ops import bootstrap


async def test_init_is_idempotent():
    settings = get_settings()
    first = await bootstrap._with_app_session(settings, bootstrap._init)
    second = await bootstrap._with_app_session(settings, bootstrap._init)
    assert first["tenant_id"] == second["tenant_id"]
    assert second["flags_created"] == []          # nothing new on the 2nd run
    assert second["flags_total"] == 3             # the three seeded module flags


async def test_create_admin_records_intent_off_public_config(client, app_session):
    settings = get_settings()
    result = await bootstrap._with_app_session(
        settings,
        lambda s: bootstrap._record_admin(s, "admin@blhsd.doh.gov.ph", "System Admin"),
    )
    assert result["bootstrap_admin"]["email"] == "admin@blhsd.doh.gov.ph"

    # Persisted into the non-public settings bag...
    tenant = (
        await app_session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one()
    assert tenant.settings["bootstrap_admin"]["name"] == "System Admin"

    # ...but NEVER exposed by the unauthenticated config endpoint.
    body = (await client.get("/api/v1/config")).json()
    assert "bootstrap_admin" not in json.dumps(body)
    assert "admin@blhsd.doh.gov.ph" not in json.dumps(body)


async def test_load_fixtures_creates_and_is_idempotent(app_session):
    settings = get_settings()
    await bootstrap._with_app_session(settings, bootstrap._load_fixtures)
    second = await bootstrap._with_app_session(settings, bootstrap._load_fixtures)
    assert second["activities_created"] == []  # idempotent (2nd run adds nothing)

    titles = {spec["title"] for spec in bootstrap._FIXTURE_ACTIVITIES}
    present = set(
        (
            await app_session.execute(
                select(Activity.title).where(Activity.title.in_(titles))
            )
        ).scalars().all()
    )
    assert present == titles


async def test_seed_workflows_is_idempotent(app_session):
    """R-4-app: ``seed-workflows`` authors + publishes the module definitions
    once; a re-run NEVER mints a new version (a chain change is an explicit
    authored v2). R-6-liq-chain: BOTH chains, reported per definition."""
    settings = get_settings()
    first = await bootstrap._with_app_session(settings, bootstrap._seed_workflows)
    second = await bootstrap._with_app_session(settings, bootstrap._seed_workflows)

    by_code = {row["definition"]: row for row in first["definitions"]}
    assert set(by_code) == {"reimbursement.claim", "reimbursement.liquidation"}
    for row in second["definitions"]:
        assert row["created"] is False
        assert row["version_no"] == by_code[row["definition"]]["version_no"]

    from office_connect.core.models import (
        WorkflowDefinition,
        WorkflowDefinitionVersion,
    )

    published = (
        await app_session.execute(
            select(WorkflowDefinitionVersion)
            .join(
                WorkflowDefinition,
                WorkflowDefinition.id == WorkflowDefinitionVersion.definition_id,
            )
            .where(
                WorkflowDefinition.code == "reimbursement.claim",
                WorkflowDefinitionVersion.is_published.is_(True),
            )
        )
    ).scalars().all()
    assert len(published) == 1


async def test_load_reference_applies_module_seeds(app_session):
    """R-4-app closed the 'module seeds only run from tests' gap: a full
    load-reference also applies the reimbursement config pack (idempotently);
    a filtered run skips module seeds."""
    settings = get_settings()
    full = await bootstrap._with_app_session(
        settings, lambda s: bootstrap._load_reference(s, settings.app_env, None)
    )
    assert "reimbursement" in full["module_datasets"]

    filtered = await bootstrap._with_app_session(
        settings,
        lambda s: bootstrap._load_reference(s, settings.app_env, {"holidays_2026"}),
    )
    assert filtered["module_datasets"] == {}


async def test_load_fixtures_refused_in_production(monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "get_settings", lambda: Settings(app_env="production"))
    rc = bootstrap.main(["load-fixtures"])
    assert rc == 1
    assert "production" in capsys.readouterr().err


def test_send_test_email_via_cli(capsys):
    # Sync test: send-test-email now flows through the outbox (send_notification
    # runs asyncio.run internally), so it must be called from a sync context —
    # exactly as the real CLI invokes it. No running event loop here.
    rc = bootstrap.main(["send-test-email", "--to", "test@example.com"])
    assert rc == 0
    assert '"driver": "log"' in capsys.readouterr().out  # dev auto-selects log


def test_read_directory_csv_parses_rows(tmp_path):
    # The CLI's CSV parse (transport) feeds row mappings to the format-agnostic
    # core ingest service; a UTF-8 BOM (spreadsheet export) is tolerated.
    org = tmp_path / "org_units.csv"
    org.write_text(
        "code,name,kind,parent_code\nBUR,Bureau,office,\nBUR-D,Div,division,BUR\n",
        encoding="utf-8-sig",
    )
    rows = bootstrap._read_directory_csv(str(org))
    assert [r["code"] for r in rows] == ["BUR", "BUR-D"]
    assert rows[1]["parent_code"] == "BUR"
    assert bootstrap._read_directory_csv(None) == []
