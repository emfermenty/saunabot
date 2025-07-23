from logging.config import fileConfig
from sqlalchemy import create_engine
from alembic import context
import sys
import os

# Добавляем путь к проекту в PYTHONPATH
sys.path.append(os.getcwd())

# Импортируем Base из вашего файла models
from Models import Base

# Получаем конфиг Alembic
config = context.config

# Настраиваем логгирование
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Указываем метаданные для миграций
target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в offline режиме."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True  # Важно для SQLite
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Запуск миграций в online режиме."""
    connectable = create_engine(config.get_main_option("sqlalchemy.url"))

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True  # Важно для SQLite
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()