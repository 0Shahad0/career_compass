import ipaddress
import json
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from openai import OpenAI

from backend.config import settings
from backend.schemas.profile import ProfileExtractionDraft


client = OpenAI(
    api_key=settings.openai_api_key
)

PORTFOLIO_MODEL = "gpt-4.1-mini"


class PortfolioHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []
        self.skip_content = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip_content = True

        if tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self.links.append(value)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip_content = False

    def handle_data(self, data):
        if not self.skip_content:
            text = data.strip()
            if text:
                self.text_parts.append(text)


def validate_portfolio_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return False

    if not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()

    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return False

    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            proto=socket.IPPROTO_TCP
        )

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return False

    except socket.gaierror:
        return False

    return True


def fetch_portfolio(url: str) -> str:
    if not validate_portfolio_url(url):
        raise ValueError("Invalid or unsafe portfolio URL.")

    response = requests.get(
        url,
        timeout=10,
        headers={
            "User-Agent": "CareerCompass/1.0"
        },
        allow_redirects=False,
    )

    response.raise_for_status()

    content_type = response.headers.get(
        "content-type",
        ""
    ).lower()

    if "text/html" not in content_type:
        raise ValueError(
            "The portfolio URL does not point to an HTML page."
        )

    parser = PortfolioHTMLParser()
    parser.feed(response.text)

    text = " ".join(parser.text_parts)

    return text[:30000]


def make_strict_schema(schema: dict) -> dict:
    if isinstance(schema, dict):

        # OpenAI structured outputs does not accept format: "uri"
        schema.pop("format", None)

        if schema.get("type") == "object":
            schema["additionalProperties"] = False

            if "properties" in schema:
                schema["required"] = list(
                    schema["properties"].keys()
                )

        for value in schema.values():
            if isinstance(value, dict):
                make_strict_schema(value)

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        make_strict_schema(item)

    return schema


def extract_portfolio_profile(url: str) -> ProfileExtractionDraft:
    portfolio_text = fetch_portfolio(url)

    if not portfolio_text.strip():
        raise ValueError(
            "Could not extract readable content from the portfolio."
        )

    prompt = f"""
Analyze the following personal portfolio website content.

Portfolio URL:
{url}

Extract only information that is explicitly supported
by the provided content.

Focus on:
- Personal information
- Professional summary
- Education
- Work experience
- Skills
- Certifications
- Projects
- Languages
- Professional links
- Achievements
- Volunteering

Important:
- Do not invent information.
- If information is missing, leave it empty.
- Projects should include technologies when clearly mentioned.
- Use the portfolio URL as the source for extracted portfolio information.
- This is an extraction draft and will be reviewed by the user.

Portfolio content:
{portfolio_text}
"""

    response = client.responses.create(
        model=PORTFOLIO_MODEL,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "portfolio_profile_extraction",
                "strict": True,
                "schema": make_strict_schema(
                    ProfileExtractionDraft.model_json_schema()
                ),
            }
        },
    )

    if not response.output_text:
        raise ValueError(
            "The AI returned an empty extraction result."
        )

    try:
        data = json.loads(response.output_text)

        result = ProfileExtractionDraft.model_validate(data)

        return result

    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(
            "Could not parse the portfolio extraction result."
        ) from exc
