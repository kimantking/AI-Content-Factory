"""ContentExtractor + ContentCleaner + SemanticChunker.

Never hands raw page HTML to an LLM. Strips navigation / footer / ads / cookie
banners / recommendation rails / tracking / <script> / <style> / repeated menus,
then extracts title / author / publisher / dates / headings / main text / tables /
important links / source references. Long documents are split into semantic
chunks so an agent retrieves only what it needs.

stdlib only (`html.parser`, `re`) — no new dependency.
"""
from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser

_DROP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "button",
              "nav", "footer", "aside", "header"}
_DROP_ROLE = {"navigation", "banner", "complementary", "contentinfo", "search", "menu"}
_DROP_CLASS_HINT = re.compile(
    r"(nav|menu|footer|header|sidebar|breadcrumb|cookie|consent|gdpr|advert|\bads?\b|"
    r"promo|newsletter|subscribe|social|share|related|recommend|comment|popup|modal|"
    r"tracking|analytics|paywall|toolbar|pagination|tag-list|author-box)", re.I)
_BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
               "td", "th", "figcaption", "dd", "dt"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._skip_stack: list[str] = []
        self.blocks: list[tuple[str, str]] = []      # (tag, text)
        self.links: list[tuple[str, str]] = []       # (href, anchor)
        self.meta: dict[str, str] = {}
        self._cur_tag: str | None = None
        self._buf: list[str] = []
        self._title_buf: list[str] = []
        self._in_title = False
        self._cur_href: str | None = None
        self._anchor: list[str] = []

    # -- helpers
    def _attrs(self, attrs):
        return {k.lower(): (v or "") for k, v in attrs}

    def _is_junk(self, tag, a):
        if tag in _DROP_TAGS:
            return True
        if a.get("role", "").lower() in _DROP_ROLE:
            return True
        if a.get("aria-hidden") == "true":
            return True
        blob = " ".join((a.get("class", ""), a.get("id", ""), a.get("data-testid", "")))
        return bool(blob and _DROP_CLASS_HINT.search(blob))

    def handle_starttag(self, tag, attrs):
        a = self._attrs(attrs)
        if tag == "meta":
            self._meta(a)
            return
        if tag == "title":
            self._in_title = True
            return
        if self._skip_depth:
            self._skip_stack.append(tag)
            self._skip_depth += 1
            return
        if self._is_junk(tag, a):
            self._skip_depth = 1
            self._skip_stack = [tag]
            return
        if tag == "a" and a.get("href"):
            self._cur_href = a["href"]
            self._anchor = []
        if tag in _BLOCK_TAGS:
            self._flush()
            self._cur_tag = tag
            self._buf = []
        if tag == "br":
            self._buf.append(" ")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            self.meta.setdefault("title", " ".join("".join(self._title_buf).split()))
            return
        if self._skip_depth:
            if self._skip_stack and self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            self._skip_depth -= 1
            if self._skip_depth < 0:
                self._skip_depth = 0
            return
        if tag == "a" and self._cur_href is not None:
            anchor = " ".join("".join(self._anchor).split())
            if anchor:
                self.links.append((self._cur_href, anchor))
            self._cur_href = None
        if tag in _BLOCK_TAGS and self._cur_tag == tag:
            self._flush()

    def handle_data(self, data):
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._skip_depth:
            return
        if self._cur_href is not None:
            self._anchor.append(data)
        if self._cur_tag:
            self._buf.append(data)

    def _flush(self):
        if self._cur_tag and self._buf:
            txt = " ".join("".join(self._buf).split())
            if txt:
                self.blocks.append((self._cur_tag, txt))
        self._cur_tag = None
        self._buf = []

    def _meta(self, a):
        name = (a.get("name") or a.get("property") or a.get("itemprop") or "").lower()
        content = a.get("content", "").strip()
        if not content:
            return
        m = {
            "author": "author", "article:author": "author", "byl": "author",
            "publisher": "publisher", "og:site_name": "publisher",
            "article:published_time": "published_at", "datepublished": "published_at",
            "date": "published_at",
            "article:modified_time": "updated_at", "datemodified": "updated_at",
            "og:title": "title", "og:description": "description",
            "og:type": "og_type", "content-language": "language", "language": "language",
        }.get(name)
        if m and not self.meta.get(m):
            self.meta[m] = content


def clean_and_extract(html: str, *, url: str = "") -> dict:
    """ContentCleaner + ContentExtractor. Returns a structured document."""
    p = _Extractor()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # noqa: BLE001 — malformed HTML must not crash learning
        pass
    p._flush()

    headings = [t for tag, t in p.blocks if tag in _HEADING_TAGS]
    body_blocks = [t for tag, t in p.blocks if tag not in _HEADING_TAGS]
    # dedup consecutive repeated lines (menus that slipped through)
    seen: set[str] = set()
    uniq: list[str] = []
    for b in body_blocks:
        k = b.lower()
        if k in seen and len(b) < 80:
            continue
        seen.add(k)
        uniq.append(b)
    main_text = "\n".join(uniq).strip()

    tables = [t for tag, t in p.blocks if tag in ("td", "th")]
    ext_links = [{"href": h, "anchor": anc} for h, anc in p.links
                 if h.startswith(("http://", "https://")) and len(anc) > 3][:40]
    src_refs = [l for l in ext_links if re.search(
        r"(source|reference|study|report|paper|doi\.org|arxiv|\.gov|\.edu|dataset)", l["href"], re.I)][:20]

    return {
        "url": url,
        "title": p.meta.get("title", "") or (headings[0] if headings else ""),
        "author": p.meta.get("author", ""),
        "publisher": p.meta.get("publisher", ""),
        "published_at": p.meta.get("published_at", ""),
        "updated_at": p.meta.get("updated_at", ""),
        "language": p.meta.get("language", "")[:12],
        "description": p.meta.get("description", ""),
        "og_type": p.meta.get("og_type", ""),
        "headings": headings[:60],
        "main_text": main_text,
        "tables": tables[:200],
        "links": ext_links,
        "source_references": src_refs,
        "char_count": len(main_text),
    }


def extract_plaintext(text: str, *, url: str = "") -> dict:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return {
        "url": url, "title": lines[0][:200] if lines else "", "author": "", "publisher": "",
        "published_at": "", "updated_at": "", "language": "", "description": "",
        "og_type": "", "headings": [l for l in lines if len(l) < 80][:40],
        "main_text": "\n".join(lines), "tables": [], "links": [], "source_references": [],
        "char_count": len("\n".join(lines)),
    }


# --------------------------------------------------------------------- #
#  SemanticChunker
# --------------------------------------------------------------------- #

def _approx_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def chunk(doc: dict, *, target_tokens: int = 400, max_tokens: int = 700) -> list[dict]:
    """Heading-aware chunking. Each chunk keeps its heading + position (0..1)."""
    text = doc.get("main_text", "") or ""
    if not text.strip():
        return []
    headings = set(doc.get("headings", []))
    paras = [pp.strip() for pp in re.split(r"\n{1,}", text) if pp.strip()]
    chunks: list[dict] = []
    cur: list[str] = []
    cur_tokens = 0
    cur_heading = doc.get("title", "")[:200]
    total = len(paras) or 1

    def _emit(idx_start):
        if not cur:
            return
        body = "\n".join(cur).strip()
        chunks.append({
            "chunk_index": len(chunks),
            "heading": cur_heading,
            "position": round(idx_start / total, 4),
            "content_hash": hashlib.sha256(body.encode()).hexdigest(),
            "token_count": _approx_tokens(body),
            "text": body,
        })

    start_idx = 0
    for i, para in enumerate(paras):
        if para in headings and len(para) < 120:
            _emit(start_idx)
            cur, cur_tokens, cur_heading, start_idx = [], 0, para, i
            continue
        pt = _approx_tokens(para)
        if cur and cur_tokens + pt > max_tokens:
            _emit(start_idx)
            cur, cur_tokens, start_idx = [], 0, i
        cur.append(para)
        cur_tokens += pt
        if cur_tokens >= target_tokens:
            _emit(start_idx)
            cur, cur_tokens, start_idx = [], 0, i + 1
    _emit(start_idx)
    return chunks
