from typing import List, Optional
from pydantic import BaseModel, Field

class ImagePlaceholder(BaseModel):
    alt_text: str = Field(..., description="SEO-optimized alt text that accurately describes the image content.")
    suggested_prompt: Optional[str] = Field(None, description="AI-generated text prompt to guide the design team in creating the image for the blog post.")

class Section(BaseModel):
    heading: str = Field(..., description="The title of the section, typically formatted as an H2 or H3 heading.")
    content: str = Field(..., description="The main body text of the section, written in Markdown format.")
    hyperlinks: List[str] = Field(default_factory=list, description="A list of external or internal URLs referenced in this section.")

class BlogArticle(BaseModel):
    title: str = Field(..., description="The primary headline of the blog post.")
    meta_description: str = Field(..., description="A concise, SEO-friendly summary of the blog post (maximum 160 characters).")
    keywords: List[str] = Field(..., description="A list of relevant SEO keywords to improve the discoverability of the blog.")
    introduction: str = Field(..., description="Introductory paragraph(s) that introduce the blog topic, formatted in Markdown.")
    sections: List[Section] = Field(..., description="The main content sections of the blog post, each with its own heading, content, and links.")
    conclusion: str = Field(..., description="A concluding paragraph that wraps up the article, also in Markdown format.")
    references: List[str] = Field(default_factory=list, description="A list of external references that are strictly relevant to the blog title and content.")
    final_image: ImagePlaceholder = Field(..., description="A single image to be placed at the end of the blog, with SEO alt text and an optional AI-generated prompt. Description should be in details simpel and easy to understand so that our ui team will easily understand and make a image")