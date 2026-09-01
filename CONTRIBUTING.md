# Contributing

Keep `main` deployable. Use `feat/<name>`, `fix/<name>`, or `chore/<name>` branches.

Use concise commit messages such as:

```text
feat: add historical import reconciliation
fix: prevent duplicate patient phone assignment
chore: improve repository CI
```

Before pushing, run backend lint/compile/tests and frontend lint/typecheck. Use pull requests for migrations, payment/package logic, booking behavior, identity matching, integrations, or multi-module changes. Every schema change must use Alembic.
