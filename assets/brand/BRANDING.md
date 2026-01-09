# Water AInalytics US — Branding Assets

This folder contains the default branding set for **Water AInalytics US**.

## Files

- `login_banner.png`  
  Wide banner intended for the login screen (light background).

- `logo_banner_dark.png`  
  Wide banner intended for dark UI contexts (e.g., dark-mode login background or hero blocks).

- `sidebar_icon.png`  
  Square icon (512×512) for light UI contexts (sidebar/top).

- `sidebar_icon_dark.png`  
  Square icon (512×512) for dark UI contexts (sidebar/top).

- `favicon_32x32.png`, `favicon_16x16.png`  
  Favicons for browser tabs.

- `palette.json`  
  Canonical color palette for UI theming.

## Streamlit integration (where to change)

### 1) Favicon / tab icon
In `app.py`:
```python
st.set_page_config(
    page_title=f"{S.APP_TITLE} — {APP_VERSION}",
    page_icon="assets/favicon_32x32.png",  # or favicon_16x16.png
    layout="wide",
)
```

### 2) Sidebar top logo / banner
Where you render the sidebar header (e.g., in `app.py` before the Session expander):
```python
st.sidebar.image("assets/sidebar_icon.png", width=72)
# or for dark mode:
# st.sidebar.image("assets/sidebar_icon_dark.png", width=72)
```

### 3) Login screen banner
In `core/auth/login_ui.py` (inside the centered column, above the title):
```python
st.image("assets/login_banner.png", width='stretch')
```

## Notes
- Keep these assets under version control (recommended) because they are lightweight and define your app identity.
- If you later implement a theme toggle (light/dark), select between `sidebar_icon.png` and `sidebar_icon_dark.png` accordingly.
