"""Jinja template rendering for prompt text."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

logger = logging.getLogger(__name__)


class TemplateManager:
    """Cached Jinja environment for repo-packaged prompt templates."""

    env: Environment

    def __init__(self) -> None:
        self.env = Environment(
            loader=PackageLoader("src", "templates"),
            autoescape=select_autoescape(enabled_extensions=(), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
            undefined=StrictUndefined,
        )
        self.env.filters["join_lines"] = self._join_lines

    @staticmethod
    def _join_lines(items: list[str] | None) -> str:
        return "\n".join(items or [])

    def render(self, template_name: str, context: dict[str, Any]) -> str:
        logger.debug("Rendering prompt template %s", template_name)
        template = self.env.get_template(template_name)
        return template.render(**context).strip()


@lru_cache(maxsize=1)
def get_template_manager() -> TemplateManager:
    return TemplateManager()


def render_template(template_name: str, context: dict[str, Any]) -> str:
    return get_template_manager().render(template_name, context)
