import os

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://ci_user:ci_password@localhost:5432/ci_db",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql+psycopg://ci_user:ci_password@localhost:5432/ci_db",
)
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test_dummy")
os.environ.setdefault("SUPABASE_SECRET_KEY", "sb_secret_test_dummy")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DOCS_ENABLED", "false")
os.environ.setdefault("CORS_ORIGINS", "[]")
