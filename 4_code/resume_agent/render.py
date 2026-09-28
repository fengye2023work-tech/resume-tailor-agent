from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .layout import LayoutSpec, load_layout_spec
from .models import ApplicationInput, ResumeContent


def render_html(
    content: ResumeContent,
    application: ApplicationInput,
    output_path: Path,
    *,
    layout_spec: LayoutSpec | None = None,
) -> Path:
    if len(content.pages) != 2:
        raise ValueError("Resume content must contain exactly two pages")
    if content.language != application.language:
        raise ValueError("Resume and application language must match")

    template_dir = Path(__file__).with_name("templates")
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(("html", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template_name = f"{content.template_family}-{content.language}.html.j2"
    template = environment.get_template(template_name)
    layout = layout_spec or load_layout_spec()
    rendered = template.render(
        content=content,
        application=application,
        language=content.language,
        profile_name=content.candidate_name,
        layout=layout,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path
