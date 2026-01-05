# Template Notes

## Create a new app from this skeleton

1. Copy this folder to a new project directory.
2. Update the app name in `core/ui/strings/en.py` (`APP_TITLE`).
3. Add domain modules under `core/` (e.g., `core/data/`, `core/map/`, `core/forecast/`).
4. Commit:

```bash
git init
git add .
git commit -m "chore: bootstrap <AppName> skeleton (v0.1.0)"
```

## Language persistence

- Stored in `.config/lang.txt`.
- Login screen allows selecting the language before authentication.
- UI text should be obtained via:

```python
from core.ui.strings.loader import get_strings
S = get_strings()
```

## Layout conventions

- Global gutters: `st.columns([1, 2, 1])`
- Login button centered: `st.columns([1, 2, 1])`
- Language selector row: `st.columns([3, 1])`
