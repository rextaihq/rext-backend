"""The emails' footer names the copyright holder as rext.ai does (A14, rext-control#534).

Rext AI is a product of Revnix LLC, so the default footer reads "© Revnix LLC, the company behind Rext
AI". A caller that passes its own company_name gets a plain line: the qualifier is Revnix's alone.
"""

from emails.components.footer import FooterProps, footer, simple_footer, standard_footer


def test_the_default_footer_names_revnix_as_the_company_behind_rext():
    for html in (simple_footer(), standard_footer(), footer()):
        assert "© Revnix LLC, the company behind Rext AI. All rights reserved." in html


def test_another_company_name_reads_plainly():
    for html in (standard_footer(company_name="Acme"), footer(FooterProps(company_name="Acme"))):
        assert "© Acme. All rights reserved." in html
        assert "behind Rext AI" not in html


def test_the_standard_footer_links_to_rext_ai_pages_that_exist():
    html = standard_footer()
    for url in (
        "https://rext.ai/help",
        "https://rext.ai/privacy-policy",
        "https://rext.ai/terms-and-conditions",
    ):
        assert f'href="{url}"' in html
    assert "help.rext.ai" not in html
