from nicegui import ui

# Utrecht University palette: yellow, red, black and white are the primary
# colours; the rest are secondary colours, meant for charts and status tints.
UU_YELLOW = "#FFCD00"
UU_RED = "#C00A35"
UU_CREAM = "#FFE6AB"
UU_ORANGE = "#F3965E"
UU_BURGUNDY = "#AA1555"
UU_BROWN = "#6E3B23"
UU_GREEN = "#24A793"
UU_BLUE = "#5287C6"
UU_DARK_BLUE = "#001240"
UU_PURPLE = "#5B2182"

CHART_COLORS = [
    UU_BLUE,
    UU_YELLOW,
    UU_GREEN,
    UU_ORANGE,
    UU_BURGUNDY,
    UU_PURPLE,
    UU_BROWN,
]
OTHER_COLOR = "#9E9A8E"
UNKNOWN_COLOR = "#E6E1D3"
MULTIPLE_COLOR = "#5E5A4E"

# Material Design 3 roles, built around the palette: warm neutral surfaces so
# the yellow sits comfortably, near-black text as UU uses black.
# In NiceGUI's "overrides" layer: it beats Quasar's normal rules, and its
# !important rules beat Quasar's (which sit in a later layer, and layered
# !important rules always beat unlayered ones).
THEME_CSS = f"""
@layer overrides {{
:root {{
    --md-surface: #FFFFFF;
    --md-surface-container-low: #F8F6F1;
    --md-surface-container: #F2EFE7;
    --md-surface-container-high: #ECE8DE;
    --md-on-surface: #1D1B16;
    --md-on-surface-variant: #4B4739;
    --md-outline: #7C7767;
    --md-outline-variant: #DCD7C8;
    --md-inverse-surface: #33302A;
    --md-inverse-on-surface: #F7F0E2;
}}
body {{
    background: var(--md-surface);
    color: var(--md-on-surface);
}}
.surface-low {{ background: var(--md-surface-container-low); }}
.surface-container {{ background: var(--md-surface-container); }}
.outline-variant {{ border-color: var(--md-outline-variant) !important; }}
.text-on-surface-variant {{ color: var(--md-on-surface-variant); }}
.title-small {{
    font-size: 14px;
    font-weight: 500;
    letter-spacing: 0.1px;
    color: var(--md-on-surface);
}}
.label-medium {{
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.5px;
    color: var(--md-on-surface-variant);
}}

/* Buttons: pill shaped, flat, sentence case. */
.q-btn {{
    border-radius: 9999px;
    text-transform: none;
    font-weight: 500;
    letter-spacing: 0.1px;
}}
.q-btn::before {{ box-shadow: none !important; }}
.q-btn.bg-primary, .q-btn.bg-secondary {{ color: #000 !important; }}
.q-btn.text-primary {{ color: var(--md-on-surface) !important; }}
.q-btn.disabled[class*="bg-"]:not(.q-btn-group > .q-btn) {{
    background: rgba(29, 27, 22, 0.12) !important;
    color: rgba(29, 27, 22, 0.38) !important;
    opacity: 1 !important;
}}
.q-btn--outline::before {{ border-color: var(--md-outline); }}
.q-btn.tonal {{ background: var(--md-surface-container-high); }}
.q-btn--round {{ border-radius: 50%; }}
.q-btn.fab {{ border-radius: 16px; height: 48px; }}
.q-btn-group {{ border-radius: 9999px; box-shadow: none; }}
.q-btn-group > .q-btn-item {{ border-radius: 0; }}
.q-btn-group > .q-btn-item:first-child {{ border-radius: 9999px 0 0 9999px; }}
.q-btn-group > .q-btn-item:last-child {{ border-radius: 0 9999px 9999px 0; }}
.segmented {{ border: 1px solid var(--md-outline); }}
.segmented > .q-btn-item + .q-btn-item {{
    border-left: 1px solid var(--md-outline);
}}

/* Navigation drawer items: the active one gets a cream pill. */
.nav-item {{ height: 40px; padding: 0 16px; }}
.nav-item .q-btn__content {{ gap: 12px; font-size: 14px; }}
.nav-item .q-icon {{ font-size: 20px; margin: 0; }}

/* Selection controls and focus in near-black, as UU yellow is too light for
   thin lines on white. */
.q-checkbox__inner--truthy .q-checkbox__svg,
.q-checkbox__inner--indet .q-checkbox__svg {{ color: #000; }}
.q-radio__inner--truthy {{ color: var(--md-on-surface); }}
.q-field--focused .q-field__control.text-primary {{
    color: var(--md-on-surface) !important;
}}
.q-menu .q-item.text-primary {{
    color: var(--md-on-surface);
    background: {UU_CREAM};
}}
a.nicegui-link {{
    color: var(--md-on-surface);
    text-decoration: underline;
    text-decoration-color: {UU_YELLOW};
    text-decoration-thickness: 2px;
    text-underline-offset: 3px;
}}

.q-tooltip {{
    background: var(--md-inverse-surface);
    color: var(--md-inverse-on-surface);
    font-size: 12px;
    border-radius: 4px;
    padding: 4px 8px;
}}
.q-dialog__inner > .q-card {{
    border-radius: 28px;
    padding: 12px;
    background: var(--md-surface-container-high);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}}
.q-table--bordered {{
    border-color: var(--md-outline-variant);
    border-radius: 12px;
}}
.q-table thead tr {{ background: var(--md-surface-container); }}
.q-table th {{ font-weight: 600; color: var(--md-on-surface-variant); }}
.q-table td, .q-table th, .q-table tr {{ border-color: var(--md-outline-variant); }}
.q-expansion-item .q-item {{ border-radius: 12px; }}
.q-separator {{ background: var(--md-outline-variant); }}
.nicegui-aggrid {{
    --ag-font-family: inherit;
    --ag-foreground-color: var(--md-on-surface);
    --ag-accent-color: var(--md-on-surface);
    --ag-border-color: var(--md-outline-variant);
    --ag-row-border-color: var(--md-outline-variant);
    --ag-wrapper-border-radius: 12px;
    --ag-header-background-color: var(--md-surface-container);
    --ag-row-hover-color: var(--md-surface-container-low);
    --ag-selected-row-background-color: rgba(255, 205, 0, 0.18);
    --ag-checkbox-checked-background-color: {UU_YELLOW};
    --ag-checkbox-checked-border-color: {UU_YELLOW};
    --ag-checkbox-checked-shape-color: #000;
    --ag-checkbox-indeterminate-background-color: {UU_YELLOW};
    --ag-checkbox-indeterminate-border-color: {UU_YELLOW};
    --ag-checkbox-indeterminate-shape-color: #000;
}}

/* Status tints, used by name across the mapping, parsing and export views. */
.bg-green-2 {{ background: #D6EFEA !important; }}
.bg-orange-2 {{ background: #FDE6D8 !important; }}
.bg-red-2 {{ background: #F6D3DC !important; }}
.bg-blue-2 {{ background: #DCE7F4 !important; }}
.text-green {{ color: {UU_GREEN} !important; }}
.text-orange {{ color: {UU_ORANGE} !important; }}
.text-red {{ color: {UU_RED} !important; }}
.text-blue {{ color: {UU_BLUE} !important; }}

::-webkit-scrollbar {{ width: 12px; height: 12px; }}
::-webkit-scrollbar-thumb {{
    background: var(--md-outline-variant);
    border: 3px solid transparent;
    border-radius: 9999px;
    background-clip: content-box;
}}
::-webkit-scrollbar-thumb:hover {{
    background: var(--md-outline);
    background-clip: content-box;
}}
}}
"""


def apply_theme() -> None:
    ui.colors(
        primary=UU_YELLOW,
        secondary=UU_CREAM,
        accent=UU_BLUE,
        positive=UU_GREEN,
        negative=UU_RED,
        info=UU_BLUE,
        warning=UU_ORANGE,
    )
    ui.add_css(THEME_CSS)
