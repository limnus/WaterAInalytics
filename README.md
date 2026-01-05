# Streamlit App Foundation (Skeleton) — v0.1.0

Reusable project skeleton for research-oriented Streamlit applications.

Includes:
- Local authentication (SQLite + Argon2): Admin / User
- Anonymous Playground mode
- Session timeout handling
- Language selector on login screen with persistence (.config/lang.txt)
- i18n-ready string modules (en / fr / pt_br)
- RBAC scaffolding
- Dark mode default via Streamlit theme config
- Centered layout gutters using column-based layout

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Admin access

On first run, an **Admin** user is created automatically.
To (re)create or reset Admin credentials:

```bash
python -m core.auth.admin_reset
```

## Self-tests

```bash
python -m core.auth.storage
python -m core.auth.session
python -m core.ui.strings.loader
python -m core.rbac.permissions
```
