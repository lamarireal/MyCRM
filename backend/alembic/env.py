from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from mycrm.core.config import get_settings
from mycrm.core.database import Base
from mycrm.modules.activities import models as activity_models  # noqa: F401
from mycrm.modules.audit import models as audit_models  # noqa: F401
from mycrm.modules.companies import models as company_models  # noqa: F401
from mycrm.modules.contacts import models as contact_models  # noqa: F401
from mycrm.modules.deals import models as deal_models  # noqa: F401
from mycrm.modules.identity import models as identity_models  # noqa: F401
from mycrm.modules.notes import models as note_models  # noqa: F401
from mycrm.modules.pipelines import models as pipeline_models  # noqa: F401
from mycrm.modules.tasks import models as task_models  # noqa: F401
from mycrm.modules.workspaces import models as workspace_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
