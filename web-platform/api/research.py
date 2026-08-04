from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from shared.errors import PlatformError


MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_SOURCE_TEXT = 200_000
MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)


@dataclass(frozen=True)
class ResearchSource:
    evidence_id: str
    requested_url: str
    final_url: str
    text: str
    sha256: str
    content_type: str

    def prompt_payload(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "url": self.final_url,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "text": self.text,
        }


def _validate_ip(value: str) -> None:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise PlatformError("source_url_blocked", "Research sources must resolve only to public internet addresses.", 400)


async def validate_public_url(url: str) -> str:
    if len(url) > 2_000:
        raise PlatformError("source_url_invalid", "Research source URL is too long.", 400)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise PlatformError("source_url_invalid", "Research sources must use a public HTTPS URL without credentials.", 400)
    try:
        if parsed.port not in {None, 443}:
            raise PlatformError("source_url_invalid", "Research sources must use the standard HTTPS port.", 400)
        _validate_ip(parsed.hostname)
    except ValueError:
        try:
            records = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise PlatformError("source_unavailable", "A research source hostname could not be resolved.", 400) from exc
        addresses = {record[4][0] for record in records}
        if not addresses:
            raise PlatformError("source_unavailable", "A research source hostname had no addresses.", 400)
        for address in addresses:
            _validate_ip(address)
    return url


def _extract_text(data: bytes, content_type: str) -> str:
    decoded = data.decode("utf-8", errors="replace")
    if content_type.startswith("text/plain"):
        return decoded[:MAX_SOURCE_TEXT]
    parser = _TextExtractor()
    parser.feed(decoded)
    return re.sub(r"\s+", " ", "\n".join(parser.parts)).strip()[:MAX_SOURCE_TEXT]


class ResearchFetcher:
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def fetch(self, url: str, evidence_id: str) -> ResearchSource:
        current = await validate_public_url(url)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                headers={"User-Agent": "CareerFlow-Research/1.0"},
            ) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    async with client.stream("GET", current) as response:
                        network_stream = response.extensions.get("network_stream")
                        peer = network_stream.get_extra_info("server_addr") if network_stream else None
                        if not peer or not isinstance(peer, tuple) or not peer:
                            raise PlatformError("source_peer_unverified", "The research source network address could not be verified.", 400)
                        _validate_ip(str(peer[0]))
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise PlatformError("source_unavailable", "A research source returned an invalid redirect.", 400)
                            current = await validate_public_url(urljoin(current, location))
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                        if not any(content_type.startswith(item) for item in ALLOWED_TYPES):
                            raise PlatformError("source_type_unsupported", "Research sources must be HTML or plain text.", 400)
                        size = 0
                        chunks: list[bytes] = []
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_SOURCE_BYTES:
                                raise PlatformError("source_too_large", "A research source exceeded 2 MB.", 413)
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        text = _extract_text(data, content_type)
                        if len(text) < 80:
                            raise PlatformError("source_content_insufficient", "A research source did not contain enough readable text.", 400)
                        return ResearchSource(
                            evidence_id=evidence_id,
                            requested_url=url,
                            final_url=current,
                            text=text,
                            sha256=hashlib.sha256(data).hexdigest(),
                            content_type=content_type,
                        )
        except httpx.HTTPStatusError as exc:
            raise PlatformError("source_unavailable", f"A research source returned HTTP {exc.response.status_code}.", 400) from exc
        except httpx.HTTPError as exc:
            raise PlatformError("source_unavailable", "A research source could not be retrieved.", 400) from exc
        raise PlatformError("source_redirect_limit", "A research source redirected too many times.", 400)

    async def fetch_all(self, urls: list[str]) -> list[ResearchSource]:
        sources: list[ResearchSource] = []
        for index, url in enumerate(urls, 1):
            sources.append(await self.fetch(url, f"SRC-{index:02d}"))
        return sources
