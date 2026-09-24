"""
Template Rendering Utilities

Provides utilities for rendering email templates with variable substitution.
Integrates with the base layout and component system.
"""

from typing import Any, Dict, Optional

from emails.components.base import EmailLayoutProps, email_layout


class TemplateRenderer:
    """
    Email template renderer with variable substitution.

    Supports:
    - Simple variable substitution ({{variable_name}})
    - Template composition with components
    - Layout integration
    """

    def __init__(self):
        """Initialize template renderer."""
        pass

    def render(
        self,
        template_content: str,
        context: Dict[str, Any],
        layout_props: Optional[EmailLayoutProps] = None,
        raw_fields: Optional[set] = None,
    ) -> str:
        """
        Render template with context variables.

        Performs variable substitution with HTML escaping.
        Wraps content in email layout.

        Args:
            template_content: HTML template string with {{variables}}
            context: Dictionary of variables to substitute
            layout_props: Optional layout configuration
            raw_fields: Set of variable names to skip escaping (trusted content only)

        Returns:
            Complete HTML email string

        Example:
            >>> renderer = TemplateRenderer()
            >>> template = "<h1>Hello {{name}}!</h1>"
            >>> context = {"name": "John"}
            >>> html = renderer.render(template, context)
        """
        # Substitute variables
        rendered_content = self._substitute_variables(template_content, context, raw_fields)

        # Wrap in layout
        return email_layout(rendered_content, layout_props)

    def render_without_layout(
        self, template_content: str, context: Dict[str, Any], raw_fields: Optional[set] = None
    ) -> str:
        """
        Render template without wrapping in layout.

        Useful for rendering partial content or testing.

        Args:
            template_content: HTML template string with {{variables}}
            context: Dictionary of variables to substitute
            raw_fields: Set of variable names to skip escaping (trusted content only)

        Returns:
            Rendered HTML string (without layout)
        """
        return self._substitute_variables(template_content, context, raw_fields)

    def _substitute_variables(
        self, content: str, context: Dict[str, Any], raw_fields: Optional[set] = None
    ) -> str:
        """
        Substitute variables in template content with HTML-escaped values.

        Uses simple {{variable}} syntax.
        All values are HTML-escaped by default to prevent XSS.
        Variables listed in raw_fields are inserted without escaping
        (use only for trusted, pre-sanitized content like rendered components).

        Args:
            content: Template content with {{variables}}
            context: Variable values
            raw_fields: Set of variable names to skip escaping (trusted content only)

        Returns:
            Content with variables substituted (HTML-escaped)
        """
        import html
        import re

        raw_fields = raw_fields or set()
        result = content

        pattern = r"\{\{(\w+)\}\}"

        def replace_variable(match):
            var_name = match.group(1)
            value = context.get(var_name)

            if value is None:
                # Leave as-is or use fallback
                return f"[{var_name}]"

            str_value = str(value)

            # Skip escaping for explicitly trusted fields
            if var_name in raw_fields:
                return str_value

            # HTML-escape all user-supplied values
            return html.escape(str_value, quote=True)

        result = re.sub(pattern, replace_variable, result)

        return result

    def compose(self, components: list, layout_props: Optional[EmailLayoutProps] = None) -> str:
        """
        Compose multiple components into a single email.

        Args:
            components: List of HTML strings (rendered components)
            layout_props: Optional layout configuration

        Returns:
            Complete HTML email string
        """
        content = "\n".join(components)
        return email_layout(content, layout_props)


# Global renderer instance
_renderer = TemplateRenderer()


def render_template(
    template_content: str,
    context: Dict[str, Any],
    raw_fields: Optional[set] = None,
    **layout_kwargs,
) -> str:
    """
    Convenience function to render a template.

    Args:
        template_content: HTML template string with {{variables}}
        context: Dictionary of variables to substitute
        raw_fields: Set of variable names to skip escaping (trusted content only)
        **layout_kwargs: Additional layout configuration

    Returns:
        Complete HTML email string

    Example:
        >>> html = render_template(
        ...     "<h1>Hello {{name}}!</h1>",
        ...     {"name": "John"},
        ...     preview_text="Welcome email"
        ... )
    """
    layout_props = None
    if layout_kwargs:
        layout_props = EmailLayoutProps(**layout_kwargs)

    return _renderer.render(template_content, context, layout_props, raw_fields)


def compose_email(components: list, **layout_kwargs) -> str:
    """
    Convenience function to compose components.

    Args:
        components: List of HTML strings (rendered components)
        **layout_kwargs: Additional layout configuration

    Returns:
        Complete HTML email string

    Example:
        >>> from emails.components.header import simple_header
        >>> from emails.components.button import primary_button
        >>> html = compose_email([
        ...     simple_header(),
        ...     "<p>Welcome!</p>",
        ...     primary_button("Get Started", "https://app.rext.com")
        ... ])
    """
    layout_props = None
    if layout_kwargs:
        layout_props = EmailLayoutProps(**layout_kwargs)

    return _renderer.compose(components, layout_props)
