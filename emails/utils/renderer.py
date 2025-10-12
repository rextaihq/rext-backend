"""
Template Rendering Utilities

Provides utilities for rendering email templates with variable substitution.
Integrates with the base layout and component system.
"""
from typing import Dict, Any, Optional, Callable
from emails.components.base import email_layout, EmailLayoutProps


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
        layout_props: Optional[EmailLayoutProps] = None
    ) -> str:
        """
        Render template with context variables.

        Performs simple variable substitution using {{variable}} syntax.
        Wraps content in email layout.

        Args:
            template_content: HTML template string with {{variables}}
            context: Dictionary of variables to substitute
            layout_props: Optional layout configuration

        Returns:
            Complete HTML email string

        Example:
            >>> renderer = TemplateRenderer()
            >>> template = "<h1>Hello {{name}}!</h1>"
            >>> context = {"name": "John"}
            >>> html = renderer.render(template, context)
        """
        # Substitute variables
        rendered_content = self._substitute_variables(template_content, context)

        # Wrap in layout
        return email_layout(rendered_content, layout_props)

    def render_without_layout(
        self,
        template_content: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Render template without wrapping in layout.

        Useful for rendering partial content or testing.

        Args:
            template_content: HTML template string with {{variables}}
            context: Dictionary of variables to substitute

        Returns:
            Rendered HTML string (without layout)
        """
        return self._substitute_variables(template_content, context)

    def _substitute_variables(
        self,
        content: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Substitute variables in template content.

        Uses simple {{variable}} syntax.
        Missing variables are left as-is with a fallback message.

        Args:
            content: Template content with {{variables}}
            context: Variable values

        Returns:
            Content with variables substituted
        """
        result = content

        # Find all {{variable}} patterns
        import re
        pattern = r'\{\{(\w+)\}\}'

        def replace_variable(match):
            var_name = match.group(1)
            value = context.get(var_name)

            if value is None:
                # Leave as-is or use fallback
                return f"[{var_name}]"

            return str(value)

        result = re.sub(pattern, replace_variable, result)

        return result

    def compose(
        self,
        components: list,
        layout_props: Optional[EmailLayoutProps] = None
    ) -> str:
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
    **layout_kwargs
) -> str:
    """
    Convenience function to render a template.

    Args:
        template_content: HTML template string with {{variables}}
        context: Dictionary of variables to substitute
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

    return _renderer.render(template_content, context, layout_props)


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
        ...     primary_button("Get Started", "https://app.wrext.com")
        ... ])
    """
    layout_props = None
    if layout_kwargs:
        layout_props = EmailLayoutProps(**layout_kwargs)

    return _renderer.compose(components, layout_props)
