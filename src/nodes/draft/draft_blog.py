from src.states.State import AgentState
import requests
from requests.structures import CaseInsensitiveDict

def draft_blog(state: AgentState):
    approved_blogs = state.get("approved_blogs", [])
    print(f"🧾 Total approved blogs to process: {len(approved_blogs)}")

    if len(approved_blogs) == 0:
        print("⚠️ No approved blogs found in state.")
        return state

    wp_url = "https://staging.wpaegis.com/wp-json/wp/v2/posts"
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjEsIm5hbWUiOiJzdGFnaW5nX3dwYWVnaXMiLCJpYXQiOjE3NTMyNzk2MzEsImV4cCI6MTkxMDk1OTYzMX0.OWcNYsPd_C4xw_L6qBTdxe8m_W4mWAeD3lzwNFccLr4"  # replace with your full token

    for idx, blog_result in enumerate(approved_blogs):
        print(f"\n📝 Posting blog {idx + 1}: {blog_result['title']}")

        try:
            # --- Format Body Content ---
            formatted_sections = "\n\n".join(
                [f"<h2>{s['heading']}</h2>\n<p>{s['content']}</p>" for s in blog_result["sections"]]
            )

            references_html = ""
            if blog_result["references"]:
                references_html = "<h3>References</h3>\n<ul>" + "\n".join(
                    [f'<li><a href="{r}" target="_blank" rel="noopener noreferrer">{r}</a></li>' for r in blog_result["references"]]
                ) + "</ul>"

            full_content = f"""
<p>{blog_result['introduction']}</p>
{formatted_sections}
<p>{blog_result['conclusion']}</p>
{references_html}
"""

            # --- Prepare POST data with SEO info ---
            post_data = {
                "title": blog_result["title"],
                "content": full_content,
                "status": "draft",  # Change to "publish" if you want to publish immediately
                "excerpt": blog_result["meta_description"],
                "tags": blog_result["keywords"]  # We'll handle this next
            }

            # --- Create Headers ---
            headers = CaseInsensitiveDict()
            headers["Authorization"] = f"Bearer {jwt_token}"
            headers["Content-Type"] = "application/json"

            # --- Convert keywords to tag IDs ---
            tag_ids = []
            for tag in blog_result["keywords"]:
                tag_resp = requests.post(
                    "https://staging.wpaegis.com/wp-json/wp/v2/tags",
                    headers=headers,
                    json={"name": tag}
                )
                if tag_resp.status_code in [200, 201]:
                    tag_ids.append(tag_resp.json()["id"])
                elif tag_resp.status_code == 400 and "term_exists" in tag_resp.text:
                    existing = requests.get(
                        f"https://staging.wpaegis.com/wp-json/wp/v2/tags?search={tag}",
                        headers=headers
                    )
                    if existing.ok and existing.json():
                        tag_ids.append(existing.json()[0]["id"])

            if tag_ids:
                post_data["tags"] = tag_ids

            # --- POST blog to WordPress ---
            response = requests.post(
                wp_url,
                headers=headers,
                json=post_data
            )

            print("📬 Response Status:", response.status_code)
            if response.status_code == 201:
                print("✅ Blog uploaded successfully.")
                print("🔗 Link:", response.json().get("link"))
            else:
                print("❌ Failed to upload blog.")
                print("📦 Response:", response.text)

        except Exception as e:
            print(f"❗ Error while processing blog '{blog_result['title']}': {e}")

    print("✅ All approved blogs processed.")
    return state
