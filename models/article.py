import hashlib
import json
from markdownify import markdownify as html_to_markdown
from dataclasses import dataclass, field
from urllib.parse import urlparse

@dataclass
class Article:
    id: int
    title: str
    url: str
    body_html: str
    updated_at: str
    section_id: int = field(default=0)

    @property
    def slug(self) -> str:
        path = urlparse(self.url).path
        return path.rstrip("/").split("/")[-1]

    def to_markdown(self) -> str:
        """Convert content from HTML into a clean Markdown document
        with a YAML frontmatter header."""
        md_body = html_to_markdown(
            self.body_html,
            heading_style="ATX",
            bullets="-",
            code_language="",
            strip=["script", "style", "nav", "footer", "iframe"],
        ).strip()

        # Collapse runs of 3+ blank lines that markdownify sometimes leaves
        # behind after stripping tags.
        while "\n\n\n" in md_body:
            md_body = md_body.replace("\n\n\n", "\n\n")

        frontmatter = (
            "---\n"
            f"title: {json.dumps(self.title)}\n"
            f"article_id: {self.id}\n"
            f"article_url: {self.url}\n"
            f"updated_at: {self.updated_at}\n"
            "---\n\n"
        )
        return frontmatter + f"# {self.title}\n\n" + md_body + "\n"

    def content_hash(self, markdown: str) -> str:
        return hashlib.sha256(markdown.encode("utf-8")).hexdigest()