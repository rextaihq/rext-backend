from src.utils.site_compliance import detect_cookie_consent

def test_detects_osano_banner():
    html = '<script src="https://cmp.osano.com/widget.js"></script>'
    result = detect_cookie_consent(html)
    assert result["has_consent_banner"] is True
    assert result["provider"] == "osano"

def test_no_banner_on_clean_page():
    html = "<html><body>Normal page content here.</body></html>"
    result = detect_cookie_consent(html)
    assert result["has_consent_banner"] is False