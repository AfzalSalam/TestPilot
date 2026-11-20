# Database Design

```mermaid
erDiagram
  users ||--o{ projects : owns
  users ||--o{ project_members : "is member"
  projects ||--o{ project_members : has
  projects ||--o{ api_endpoints : has
  projects ||--o{ collections : has
  projects ||--o{ test_cases : has
  collections ||--o{ test_cases : groups
  api_endpoints ||--o{ test_cases : "optional link"
  projects ||--o{ schedules : has
  projects ||--o{ runs : has
  schedules ||--o{ runs : triggers
  runs ||--o{ test_results : contains
  test_cases ||--o{ test_results : "SET NULL on delete"
  projects ||--o{ api_keys : has
```

## Notes
- **Encrypted columns:** `EncryptedJSON` (Fernet) for `test_cases.auth_config` and `projects.variables`.
- **Timestamps:** `UTCDateTime` decorator returns timezone-aware UTC on every backend (SQLite drops tzinfo natively).
- **Results keep a snapshot** (name, method, url) so history survives test edits/deletes (`test_case_id` is `SET NULL`).
- **Integrity:** `UNIQUE(run_id, test_case_id)` on `test_results` prevents duplicate results under redelivery.
- **Cascades:** deleting a project removes everything under it.
- **API keys:** only a sha256 hash and a display prefix are stored.
- **Migrations:** Alembic `0001_initial_schema`; upgrade, downgrade, `alembic check` (no drift) verified on SQLite, and upgrade verified on PostgreSQL 16.
