# Configuration Reference

This document covers the settings system, environment variables, and YAML configuration files for the Lead Scoring application.

---

## Settings System

`config/settings.py` defines four Pydantic `BaseSettings` classes. Settings are loaded from environment variables; `Settings` also reads from a `.env` file at the project root.

| Class | Env prefix | Purpose |
|---|---|---|
| `Settings` | _(none)_ | Main application settings; composes the three sub-classes below |
| `DatabaseSettings` | `DB_` | PostgreSQL connection parameters |
| `CRMSettings` | `CRM_` | CRM integration credentials and type |
| `ModelSettings` | `MODEL_` | Model artifact path, version, and scoring thresholds |

`Settings` is the entry point. It holds `database`, `crm`, and `model` as nested fields constructed via `Field(default_factory=...)`, so each sub-class reads its own prefixed env vars independently.

**Accessing settings**

```python
from config.settings import get_settings

settings = get_settings()
db_url = settings.database.url
```

`get_settings()` is wrapped with `functools.lru_cache`, so settings are loaded once per process.

**YAML configs**

`Settings` exposes two properties that load YAML files from `config/`:

- `settings.features_config` — loads `config/features.yaml`
- `settings.crm_mappings` — loads `config/crm.yaml`

Both use `load_yaml_config(filename)`, which returns `{}` if the file does not exist.

---

## Environment Variables

All variables can be set in the shell or in a `.env` file at the project root. The `.env` file is only read by `Settings` (not by the sub-classes directly, but they inherit values through the composed factory).

### Application (`Settings`)

| Variable | Type | Default | Required |
|---|---|---|---|
| `APP_NAME` | str | `Lead Scoring API` | No |
| `APP_VERSION` | str | `0.1.0` | No |
| `ENVIRONMENT` | `"development"` \| `"staging"` \| `"production"` | `development` | No |
| `DEBUG` | bool | `false` | No |
| `HOST` | str | `0.0.0.0` | No |
| `PORT` | int | `8000` | No |

### Database (`DatabaseSettings`, prefix `DB_`)

| Variable | Type | Default | Required |
|---|---|---|---|
| `DB_HOST` | str | `localhost` | No |
| `DB_PORT` | int | `5432` | No |
| `DB_USER` | str | `postgres` | No |
| `DB_PASSWORD` | str | `postgres` | No |
| `DB_NAME` | str | `lead_scoring` | No |
| `DB_POOL_SIZE` | int | `5` | No |
| `DB_MAX_OVERFLOW` | int | `10` | No |

`DatabaseSettings` also exposes two computed (read-only) properties that are not set via env vars:

- `database.url` — async URL: `postgresql+asyncpg://user:password@host:port/name`
- `database.sync_url` — sync URL for Alembic: `postgresql://user:password@host:port/name`

### CRM (`CRMSettings`, prefix `CRM_`)

| Variable | Type | Default | Required |
|---|---|---|---|
| `CRM_TYPE` | `"hubspot"` \| `"salesforce"` \| `"none"` | `none` | No |
| `CRM_HUBSPOT_API_KEY` | str \| None | `None` | Conditional |
| `CRM_HUBSPOT_ACCESS_TOKEN` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_CLIENT_ID` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_CLIENT_SECRET` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_USERNAME` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_PASSWORD` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_SECURITY_TOKEN` | str \| None | `None` | Conditional |
| `CRM_SALESFORCE_DOMAIN` | str | `login` | No |

Conditional fields are only required when `CRM_TYPE` is set to the matching CRM. Use `login` for production Salesforce; use `test` for sandbox.

### Model (`ModelSettings`, prefix `MODEL_`)

| Variable | Type | Default | Required |
|---|---|---|---|
| `MODEL_ARTIFACT_PATH` | str | `models/current.joblib` | No |
| `MODEL_VERSION` | str | `v0.0.0` | No |
| `MODEL_BUCKET_A_THRESHOLD` | float | `0.7` | No |
| `MODEL_BUCKET_B_THRESHOLD` | float | `0.4` | No |
| `MODEL_BUCKET_C_THRESHOLD` | float | `0.2` | No |

The bucket thresholds define score ranges for lead grades. A score ≥ `BUCKET_A_THRESHOLD` is grade A; ≥ `BUCKET_B_THRESHOLD` is grade B; ≥ `BUCKET_C_THRESHOLD` is grade C; below that is grade D.

> **Note:** `.env.example` sets `MODEL_ARTIFACT_PATH=src/models/current.joblib`, but the code default in `settings.py` is `models/current.joblib`. When no `.env` file is present, the code default applies.

---

## YAML Configs

### `config/features.yaml`

Defines the 20 features used (or reserved) by the ML model. The file includes a top-level `version` field and a `features` list.

**File structure**

```yaml
version: "1.0"

features:
  - name: <internal_feature_name>
    category: <recency|frequency|intensity|intent|firmographic|engagement>
    type: <numeric|boolean|categorical>
    description: <human-readable description>
    default: <value>          # used when data is missing
    categories: [...]         # present only for type: categorical
```

**Categories and feature count**

| Category | Features | Notes |
|---|---|---|
| `recency` | 3 | `days_since_last_visit`, `days_since_last_email_open`, `days_since_first_touch` |
| `frequency` | 5 | page views (7d, 30d), total sessions, emails opened/clicked (30d) |
| `intensity` | 3 | avg pages/session, avg session duration, pricing page views |
| `intent` | 4 | viewed pricing, requested demo, downloaded content, visited competitor comparison |
| `firmographic` | 3 | company size bucket, industry ICP match, job title seniority |
| `engagement` | 2 | engagement velocity (7d), is engagement increasing |

**MVP status:** 17 of the 20 features are actively used in the current model. The 3 firmographic features (`company_size_bucket`, `industry_match_icp`, `job_title_seniority`) are placeholder definitions; they are not populated by the current ingestion pipeline.

**Categorical features and their allowed values**

| Feature | Categories |
|---|---|
| `company_size_bucket` | `unknown`, `1-10`, `11-50`, `51-200`, `201-1000`, `1000+` |
| `job_title_seniority` | `unknown`, `individual_contributor`, `manager`, `director`, `vp`, `c_level` |

---

### `config/crm.yaml`

Defines field mappings for CRM integrations. This config is prepared for Phase 7 (CRM sync) and is not actively used by the current API.

**File structure**

```yaml
version: "1.0"

hubspot:
  contact_fields:      # internal field name -> HubSpot property name
    ...
  output_fields:       # internal output name -> HubSpot property name
    ...
  event_types:         # internal event type -> HubSpot event type constant
    ...

salesforce:
  object_type: Lead    # or Contact
  contact_fields:      # internal field name -> Salesforce field name
    ...
  output_fields:       # internal output name -> Salesforce custom field name (__c suffix)
    ...
  event_objects:       # internal category -> Salesforce object name
    ...

company_size_mapping:  # raw CRM value -> internal bucket
  ...

icp:
  target_industries: [...]
  min_company_size: "11-50"
  decision_maker_titles: [...]
```

**HubSpot mappings**

`contact_fields` maps 12 internal contact properties (e.g., `email`, `company_name`, `job_title`) to their HubSpot property names (e.g., `email`, `company`, `jobtitle`).

`output_fields` maps 5 scoring outputs — `score`, `bucket`, `top_factors`, `scored_at`, `model_version` — to HubSpot custom properties that must be created in HubSpot before use.

`event_types` maps 5 internal event names (`pageview`, `email_open`, `email_click`, `form_submit`, `meeting_booked`) to HubSpot event type constants.

**Salesforce mappings**

`contact_fields` maps 11 internal fields to Salesforce field names (PascalCase convention, e.g., `Email`, `FirstName`, `Company`).

`output_fields` maps the same 5 scoring outputs to Salesforce custom fields (`Lead_Score__c`, etc.) that must be created before use.

`event_objects` maps internal categories (`email`, `task`, `event`) to the Salesforce object names used for activity tracking.

**Company size normalization**

`company_size_mapping` translates raw CRM values (individual integers `"1"`–`"10"` and range strings like `"11-50"`, `"201-500"`) to the internal bucket values defined in `features.yaml`.

**ICP criteria**

`icp` defines the ideal customer profile used to populate `industry_match_icp`:

- `target_industries`: 8 industries (Technology, Software, SaaS, Information Technology, Computer Software, Internet, Financial Services, Marketing and Advertising)
- `min_company_size`: `11-50`
- `decision_maker_titles`: 10 title keywords (CEO, CTO, CFO, COO, CMO, VP, Vice President, Director, Head of, Chief)

---

## `.env.example`

Located at the project root. Copy it to `.env` for local development:

```bash
cp .env.example .env
```

The file contains all env vars with safe defaults. Credentials (`DB_PASSWORD`, `CRM_HUBSPOT_ACCESS_TOKEN`, Salesforce credentials) are left blank or set to development-safe values.

**Never commit `.env` to version control.** It is listed in `.gitignore`. Only `.env.example` (with no real secrets) is committed.

The `.env.example` omits `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `HOST`, `PORT`, and `CRM_HUBSPOT_API_KEY` since their coded defaults are suitable for local development. Set them explicitly if you need non-default values.
