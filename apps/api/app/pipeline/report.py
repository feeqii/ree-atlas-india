from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .overlay import image_to_base64


def render_report(run_dir: str, run_meta: Dict, targets: List[Dict]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent.parent / "templates")),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")

    overlay_path = run_meta.get("overlay_path")
    sentinel_path = run_meta.get("sentinel_preview_path")
    hillshade_path = run_meta.get("hillshade_path")

    overlay_b64 = image_to_base64(overlay_path) if overlay_path else ""
    sentinel_b64 = image_to_base64(sentinel_path) if sentinel_path else ""
    hillshade_b64 = image_to_base64(hillshade_path) if hillshade_path else ""

    html = template.render(
        run=run_meta,
        targets=targets,
        overlay_b64=overlay_b64,
        sentinel_b64=sentinel_b64,
        hillshade_b64=hillshade_b64,
    )

    report_path = str(Path(run_dir) / "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path
