# BBB Review Portal — Streamlit deployment

This repository contains generic application code only. Document metadata, document links, connection tokens, account passwords and review records are not stored in this repository.

The app uses the existing authenticated BBB portal service. The original portal remains online and both interfaces share reviewer accounts, drafts and review records.

## Streamlit Community Cloud

- Branch: `main`
- Main file: `app.py`
- Python: 3.12 or later

Configure these values in **Advanced settings → Secrets**:

- `PORTAL_API_URL`: existing portal service origin
- `PORTAL_API_TOKEN`: existing service connection token
- `DOCUMENT_CONFIG_JSON`: JSON document configuration from the private source repository

The public app still requires its own reviewer or administrator login. Never put credentials, document links or `.streamlit/secrets.toml` in this repository.
