
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from emails.utils.renderer import TemplateRenderer

def test_xss_vulnerability():
    renderer = TemplateRenderer()
    
    # Malicious payload
    malicious_payload = '<script>alert("XSS")</script>'
    context = {"user_name": malicious_payload}
    template = "<h1>Hello {{user_name}}</h1>"
    
    # Render
    rendered = renderer.render_without_layout(template, context, raw_fields=None)
    
    # Check if payload is present as raw HTML (Vulnerable)
    print(f"Rendered Output: {rendered}")
    
    if malicious_payload in rendered:
        print("[FAIL] Vulnerability Reproduced: Malicious script rendered as raw HTML.")
    else:
        print("[PASS] Vulnerability Mitigated: Malicious script NOT rendered as raw HTML.")
        
        # Verify it is escaped
        expected_escaped = '&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;'
        # Note: quote=True escapes quotes as well
        
        if expected_escaped in rendered or expected_escaped.replace('&quot;', '"') in rendered: # Check for partial escaping if quote=True not used yet
             print("Payload is escaped.")
        else:
             print("Payload is NOT present in expected escaped form either.")

    # Test raw_fields functionality
    print("\nTesting raw_fields functionality...")
    trusted_payload = "<b>Trusted Content</b>"
    context_trusted = {"trusted_var": trusted_payload}
    template_trusted = "<div>{{trusted_var}}</div>"
    
    # Render with raw_fields
    rendered_trusted = renderer.render_without_layout(
        template_trusted, 
        context_trusted, 
        raw_fields={"trusted_var"}
    )
    
    print(f"Trusted Render Output: {rendered_trusted}")
    
    if trusted_payload in rendered_trusted:
        print("[PASS] raw_fields works: Trusted content rendered as raw HTML.")
    else:
        print("[FAIL] raw_fields failed: Trusted content was escaped or modified.")

if __name__ == "__main__":
    try:
        test_xss_vulnerability()
    except TypeError as e:
        print(f"TypeError caught (likely due to unexpected raw_fields arg before fix): {e}")
        # Rerun without raw_fields to confirm vulnerability in current state
        from emails.utils.renderer import TemplateRenderer
        renderer = TemplateRenderer()
        malicious_payload = '<script>alert("XSS")</script>'
        context = {"user_name": malicious_payload}
        template = "<h1>Hello {{user_name}}</h1>"
        # The current code DOES NOT accept raw_fields, so we call it without
        rendered = renderer.render_without_layout(template, context)
        print(f"Rendered Output (Legacy Call): {rendered}")
        if malicious_payload in rendered:
             print("[FAIL] Vulnerability Reproduced (Legacy Call): Malicious script rendered as raw HTML.")
