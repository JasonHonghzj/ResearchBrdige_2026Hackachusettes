"""Per-session app styling; does not modify the user's browser or OS appearance."""


def css(theme):
    palette = {
        "light": dict(bg="#f6f8fb", panel="#ffffff", panel2="#edf3f8", text="#142e43", muted="#526b7d", line="#dce5ed", accent="#087f8c", soft="#e5f4f4"),
        "dark": dict(bg="#101923", panel="#172534", panel2="#203347", text="#edf4fc", muted="#b0c4d7", line="#3b5166", accent="#50d4d4", soft="#193e49"),
    }[theme]
    palette["primary-text"] = "#ffffff" if theme == "light" else "#092731"
    palette["hint"] = "#7b828c" if theme == "light" else "#a6aeb8"
    variables = ";".join(f"--rb-{k}:{v}" for k, v in palette.items())
    return """<style>
    :root {VARIABLES;color-scheme:SCHEME;}
    .stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--rb-bg)!important;color:var(--rb-text)!important;}
    [data-testid="stHeader"]{background:var(--rb-bg)!important;}
    .st-key-toolbar{position:fixed;top:3px;right:126px;width:min(350px,calc(100vw - 190px));z-index:999990;gap:0!important;background:var(--rb-bg);}
    .st-key-toolbar [data-testid="stHorizontalBlock"]{flex-direction:row!important;gap:8px!important;}
    .st-key-toolbar [data-testid="stColumn"]{min-width:0!important;flex:1 1 0!important;width:auto!important;}
    .st-key-toolbar [data-testid="stColumn"]:first-child{flex:1.35 1 0!important;}
    .st-key-toolbar input{font-size:.88rem!important;}
    .st-key-toolbar [data-testid="stSelectbox"]{margin:0!important;}
    .st-key-toolbar [data-testid="stWidgetLabel"]{min-height:13px!important;margin:0 0 2px!important;}
    .st-key-toolbar [data-testid="stWidgetLabel"] p{font-size:.68rem!important;line-height:13px!important;color:var(--rb-muted)!important;}
    .st-key-toolbar .react-aria-ComboBox [role="group"]{height:30px!important;min-height:30px!important;}
    .st-key-toolbar input{height:28px!important;min-height:28px!important;}
    .st-key-toolbar button[aria-haspopup="listbox"]{height:28px!important;min-height:28px!important;width:28px!important;}
    [data-testid="stSidebar"],[data-testid="stSidebarContent"]{background:var(--rb-panel2)!important;color:var(--rb-text)!important;}
    .block-container{max-width:1320px;padding-top:3.8rem;padding-bottom:3rem;}
    h1,h2,h3,h4,h5,h6,[data-testid="stMarkdownContainer"],label,[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p{color:var(--rb-text)!important;}
    [data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--rb-muted)!important;opacity:1!important;}
    [data-testid="stMetric"]{background:var(--rb-panel);border:1px solid var(--rb-line);border-radius:12px;padding:14px 18px;}
    [data-testid="stMetricValue"],[data-testid="stMetricLabel"]{color:var(--rb-text)!important;}
    [data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--rb-line)!important;}
    input,textarea, [role="combobox"], [role="listbox"], [role="option"]{background:var(--rb-panel)!important;color:var(--rb-text)!important;border-color:var(--rb-line)!important;}
    input::placeholder,textarea::placeholder{color:var(--rb-muted)!important;}
    [role="option"][aria-selected="true"]{background:var(--rb-soft)!important;}
    .react-aria-ComboBox [role="group"],[data-testid="stMultiSelect"] [role="group"],[data-testid="stSelectboxVirtualDropdown"],[data-testid="stMultiSelectVirtualDropdown"]{background:var(--rb-panel)!important;color:var(--rb-text)!important;border-color:var(--rb-line)!important;box-shadow:none!important;}
    [role="option"] [data-item-hl]{color:inherit!important;background:transparent!important;}
    [role="option"][data-focused="true"],[role="option"][data-hovered="true"],[role="option"]:hover{background:var(--rb-soft)!important;color:var(--rb-text)!important;}
    [data-testid="stMultiSelect"] [data-rac][data-selected="true"],[data-baseweb="tag"]{background:var(--rb-soft)!important;color:var(--rb-text)!important;}
    input::selection,textarea::selection{background:var(--rb-soft)!important;color:var(--rb-text)!important;}
    [data-testid="stTextInput"]>div,[data-testid="stTextArea"]>div,[data-testid="stNumberInput"]>div,[data-testid="stSelectbox"]>div,[data-testid="stMultiSelect"]>div{background:var(--rb-panel)!important;border-color:var(--rb-line)!important;color:var(--rb-text)!important;}
    button,[data-testid="stLinkButton"] a{background:var(--rb-panel)!important;color:var(--rb-text)!important;border-color:var(--rb-line)!important;}
    button p,button svg,button span,button [data-testid="stMarkdownContainer"],[data-testid="stLinkButton"] a p{color:inherit!important;}
    button svg{fill:currentColor!important;}
    button[kind="primary"],button[data-testid^="stBaseButton-primary"]{background:var(--rb-accent)!important;color:var(--rb-primary-text)!important;}
    [role="tab"]{background:transparent!important;}
    [role="tab"][aria-selected="true"]{color:var(--rb-accent)!important;border-bottom-color:var(--rb-accent)!important;}
    a{color:var(--rb-accent);}
    summary,summary p,[data-testid="stExpander"]{background:var(--rb-panel)!important;color:var(--rb-text)!important;border-color:var(--rb-line)!important;}
    [data-testid="stAlert"]{background:var(--rb-soft)!important;color:var(--rb-text)!important;}
    [data-testid="stCode"],pre,code{background:var(--rb-panel2)!important;color:var(--rb-text)!important;}
    hr{border-color:var(--rb-line)!important;}
    .rb-kicker{font-size:.78rem;font-weight:700;letter-spacing:.13em;color:var(--rb-accent);margin:.65rem 0;}
    .rb-hero{font-size:2.3rem;font-weight:750;line-height:1.25;color:var(--rb-text);margin:.6rem 0;}
    .rb-sub{color:var(--rb-muted);font-size:1rem;line-height:1.7;margin-bottom:1.4rem;}
    .rb-example{color:var(--rb-hint);font-size:.88rem;line-height:1.7;margin:.25rem 0;}
    .rb-chain{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:15px 0;}
    .rb-node{background:var(--rb-panel);border:1px solid var(--rb-line);border-radius:10px;padding:16px;overflow-wrap:anywhere;}
    .rb-node small{display:block;color:var(--rb-accent);font-weight:700;margin-bottom:8px;}
    .rb-node strong{color:var(--rb-text);}
    .rb-table-wrap{max-height:510px;overflow:auto;margin:10px 0;border:1px solid var(--rb-line);border-radius:8px;}
    .rb-table{width:100%;border-collapse:collapse;background:var(--rb-panel);color:var(--rb-text);font-size:.88rem;}
    .rb-table th{position:sticky;top:0;background:var(--rb-panel2);text-align:left;}
    .rb-table td,.rb-table th{padding:10px 12px;border-bottom:1px solid var(--rb-line);overflow-wrap:anywhere;}
    .rb-footer{margin-top:2rem;padding-top:1rem;border-top:1px solid var(--rb-line);color:var(--rb-muted);font-size:.85rem;}
    @media(max-width:650px){.rb-hero{font-size:1.7rem;}.rb-chain{grid-template-columns:1fr;}}
    @media(max-width:440px){.st-key-toolbar{right:91px;width:calc(100vw - 142px);}.st-key-toolbar input{font-size:.75rem!important;}}
    </style>""".replace("VARIABLES", variables).replace("SCHEME", theme)
