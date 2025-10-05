from src.states.State import AgentState
import requests
from requests.structures import CaseInsensitiveDict
import markdown  
from dotenv import load_dotenv
import os

from src.api.lib.logger import auto_logger

logger = auto_logger()

load_dotenv()

def draft_blog(state: AgentState):
    approved_blogs = state.get("approved_blogs", [])
    logger.info(f"🧾 Total approved blogs to process: {len(approved_blogs)}")

    if len(approved_blogs) == 0:
        logger.info("⚠️ No approved blogs found in state.")
        return state

    wp_url = os.getenv("WP_URL")
    jwt_token = os.getenv("WP_TOKEN")

    for idx, blog_result in enumerate(approved_blogs):
        logger.info(f"\n📝 Posting blog {idx + 1}: {blog_result['title']}")

        try:
            # --- Format sections ---
            formatted_sections = ""
            for section in blog_result["sections"]:
                heading_html = f"<h2>{markdown.markdown(section['heading'])}</h2>"
                content_html = markdown.markdown(section["content"])
                formatted_sections += f"{heading_html}\n{content_html}\n\n"

            # --- References Section ---
            references_html = ""
            if blog_result["references"]:
                references_html = "<h3>References</h3>\n<ul>" + "\n".join(
                    [f'<li><a href="{r}" target="_blank" rel="noopener noreferrer">{r}</a></li>'
                     for r in blog_result["references"]]
                ) + "</ul>"

            # --- Final Image Placeholder Section ---
            image_note = ""
            final_img = blog_result.get("final_image")
            if final_img:
                image_note = f"""
            <hr>
            <h3>📌 Final Image Placeholder</h3>
            <p><strong>Alt Text:</strong> {final_img.alt_text}</p>
            <p><strong>Design Prompt:</strong> {getattr(final_img, 'suggested_prompt', 'N/A')}</p>
            """


            # --- Combine Everything ---
            full_content = f"""
{markdown.markdown(blog_result['introduction'])}
{formatted_sections}
{markdown.markdown(blog_result['conclusion'])}
{references_html}
{image_note}
"""

            # --- Prepare POST data ---
            post_data = {
                "title": blog_result["title"],
                "content": full_content,
                "status": "draft",  # or "publish"
                "excerpt": blog_result["meta_description"],
                "tags": blog_result["keywords"]
            }

            # --- Headers ---
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

            # --- POST to WordPress ---
            response = requests.post(
                wp_url,
                headers=headers,
                json=post_data
            )

            logger.info("📬 Response Status:", response.status_code)
            if response.status_code == 201:
                logger.info("✅ Blog uploaded successfully.")
                logger.info("🔗 Link:", response.json().get("link"))
            else:
                logger.info("❌ Failed to upload blog.")
                logger.info("📦 Response:", response.text)

        except Exception as e:
            logger.info(f"❗ Error while processing blog '{blog_result['title']}': {e}")

    logger.info("✅ All approved blogs processed.")
    return state
