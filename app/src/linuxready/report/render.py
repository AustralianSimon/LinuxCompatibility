from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import ScanResult

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_VERDICT_LABEL = {
    "native":         "Native Linux",
    "packaged":       "Packaged",
    "layer_excellent":"Works via Proton/Wine",
    "layer_workable": "Works with tweaks",
    "layer_poor":     "Works poorly",
    "blocked":        "Blocked",
    "replace":        "Needs replacement",
    "web":            "Web version available",
    "unknown":        "Unknown",
}

_VERDICT_CSS = {
    "native":         "v-pass",
    "packaged":       "v-pass",
    "web":            "v-pass",
    "layer_excellent":"v-pass",
    "layer_workable": "v-partial",
    "layer_poor":     "v-partial",
    "replace":        "v-fail",
    "blocked":        "v-fail",
    "unknown":        "v-unknown",
}


def render_report(result: ScanResult) -> str:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["verdict_label"] = lambda v: _VERDICT_LABEL.get(v or "unknown", "Unknown")
    env.globals["verdict_css"]   = lambda v: _VERDICT_CSS.get(v or "unknown", "v-unknown")

    tmpl = env.get_template("report.html.j2")
    migration_found = [m for m in result.migration if m.found]
    return tmpl.render(
        result          = result,
        distro_recs     = result.distro_recs,
        blockers        = [i for i in result.items if i.is_blocker],
        apps            = [i for i in result.items if i.source in ("registry_apps", "msix")],
        games           = [i for i in result.items if i.source in ("steam", "epic", "gog")],
        hardware        = [i for i in result.items if i.source in ("hardware", "firmware")],
        unknowns        = [i for i in result.items if i.verdict == "unknown"],
        migration       = migration_found,
        migration_total = round(sum(m.size_gb for m in migration_found), 1),
    )
