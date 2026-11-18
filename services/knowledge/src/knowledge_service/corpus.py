"""Only project-authored, reviewed UTF-8 Markdown claims. No runtime URL fetching."""

import hashlib
import json
from pathlib import Path
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import Field, model_validator, field_validator
from portfolio_contracts import StrictModel

PARSER = "markdown-claims-v1"
CHUNKER = "approved-claims-v1"
MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
INDEX = "openai-small-1536-v1"


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    return " ".join(
        re.findall(r"\w+", "".join(c for c in text if not unicodedata.combining(c)))
    )


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Claim(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{1,79}$")
    text: str = Field(min_length=10, max_length=2000)
    source_title: str = Field(min_length=1, max_length=300)
    source_url: str = Field(max_length=2048)
    locator: str = Field(min_length=1, max_length=300)

    @field_validator("source_url")
    @classmethod
    def https_only(cls, value):
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError("HTTPS citation required")
        return value


class DocumentInput(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=300)
    language: str = "vi"
    visibility: str
    markdown: str = Field(max_length=65536)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    published_at: datetime | None = None
    available_at: datetime
    claims: list[Claim] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def approved_markdown(self):
        if self.visibility != "PUBLIC" or self.language != "vi":
            raise ValueError("v1 accepts PUBLIC Vietnamese notes only")
        if (
            len(self.markdown.encode()) > 65536
            or sha(self.markdown) != self.content_hash
        ):
            raise ValueError("size or checksum mismatch")
        if re.search(r"[<>\x00-\x08\x0b\x0c\x0e-\x1f]", self.markdown):
            raise ValueError("HTML/script/binary forbidden")
        expected = "".join("## " + c.id + "\n" + c.text + "\n" for c in self.claims)
        if self.markdown != expected or len({c.id for c in self.claims}) != len(
            self.claims
        ):
            raise ValueError("one exact reviewed paragraph per stable claim")
        if self.available_at.tzinfo is None or (
            self.published_at and self.published_at.tzinfo is None
        ):
            raise ValueError("timezone required")
        return self


class Manifest(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    parser_version: str
    chunker_version: str
    review: str = Field(min_length=10, max_length=1000)
    documents: list[DocumentInput] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def bounded(self):
        if self.parser_version != PARSER or self.chunker_version != CHUNKER:
            raise ValueError("unsupported parser/chunker version")
        if (
            len(self.model_dump_json().encode()) > 1048576
            or sum(len(d.claims) for d in self.documents) > 1000
        ):
            raise ValueError("batch budget")
        if len({d.key for d in self.documents}) != len(self.documents):
            raise ValueError("duplicate document key")
        claims = [c.id for d in self.documents for c in d.claims]
        if len(claims) != len(set(claims)):
            raise ValueError("duplicate claim ID")
        return self


def load_manifest(root):
    root = Path(root).resolve(strict=True)
    path = root / "manifest.json"
    if path.is_symlink() or path.stat().st_size > 1048576:
        raise ValueError("manifest boundary")
    data = json.loads(path.read_text(encoding="utf-8"))
    total = path.stat().st_size
    for doc in data.get("documents", []):
        relative = Path(doc.pop("path"))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".md":
            raise ValueError("path boundary")
        target = (root / relative).resolve(strict=True)
        if not target.is_relative_to(root) or target.stat().st_size > 65536:
            raise ValueError("file boundary")
        total += target.stat().st_size
        if total > 1048576:
            raise ValueError("batch budget")
        doc["markdown"] = target.read_text(encoding="utf-8")
    return Manifest.model_validate(data)
