"""
Parse PDF, DOCX, TXT, and MD files into chunks.

Chunking strategies:
  .md  — section-aware: split on ## boundaries first, token-split within each section.
         No cross-section overlap. Heading text is kept as the first line of each chunk.
  rest — recursive strategy: coarsest separator first, recurse on oversized pieces,
         one-segment overlap between chunks.

Heading extraction always runs on the RAW source text so ## markers are visible.
"""
import re
from pathlib import Path

import tiktoken

TOKENIZER = tiktoken.get_encoding("cl100k_base")
CHUNK_TOKENS = 400
SEPARATORS = ["\n\n\n", "\n\n", "\n", ". ", "! ", "? ", " "]


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_file(path: str | Path) -> str:
    """Return the full text of a document (markdown syntax stripped for non-MD)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(path)
    elif suffix in (".docx", ".doc"):
        return _parse_docx(path)
    elif suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".md":
        raw = path.read_text(encoding="utf-8", errors="replace")
        return _strip_md(raw)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def _parse_pdf(path: Path) -> str:
    import fitz
    doc = fitz.open(str(path))
    pages = [page.get_text("text").strip() for page in doc if page.get_text("text").strip()]
    doc.close()
    return "\n\n".join(pages)


def _parse_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def _strip_md(text: str) -> str:
    """Strip markdown syntax to plain readable text. Keep heading text (strip # marker only)."""
    # Fenced code blocks — keep content
    text = re.sub(r'```[^\n]*\n(.*?)```', r'\1', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Headings — strip # marker, keep text
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Bold / italic
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    # Links — keep display text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Images
    text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    # HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Blockquote markers
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # Collapse excess blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, is_markdown: bool = False, raw_md: str | None = None) -> list[str]:
    """
    For markdown: section-aware split on ## boundaries, no cross-section overlap.
    For other formats: recursive split with one-segment overlap.
    """
    if is_markdown and raw_md:
        return _chunk_markdown(raw_md)
    return _recursive_split(text.strip(), SEPARATORS)


def _chunk_markdown(raw: str) -> list[str]:
    """
    Split markdown into one chunk per ## section.
    Each chunk starts with the section heading (plain text) so the embedding
    model knows what topic the chunk covers.
    If a section exceeds CHUNK_TOKENS it is split further (no overlap).
    """
    # Split at every H1/H2/H3 boundary; lookahead keeps the heading with its section
    sections = re.split(r'(?=^#{1,3} )', raw, flags=re.MULTILINE)

    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        clean = _strip_md(section).strip()
        if not clean:
            continue
        tokens = len(TOKENIZER.encode(clean))
        if tokens <= CHUNK_TOKENS:
            chunks.append(clean)
        else:
            # Section too long — split recursively but without overlap
            chunks.extend(_recursive_split_no_overlap(clean, SEPARATORS))

    return [c.strip() for c in chunks if c.strip()]


def _recursive_split(text: str, separators: list[str]) -> list[str]:
    """Recursive chunker with one-segment overlap (used for PDF/DOCX/TXT)."""
    if not text.strip():
        return []
    if len(TOKENIZER.encode(text)) <= CHUNK_TOKENS:
        return [text]
    if not separators:
        return _hard_split(text)

    sep, rest = separators[0], separators[1:]
    parts = [p for p in text.split(sep) if p.strip()]

    if len(parts) == 1:
        return _recursive_split(text, rest)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in parts:
        pt = len(TOKENIZER.encode(part))
        if current_tokens + pt > CHUNK_TOKENS and current:
            merged = sep.join(current)
            if len(TOKENIZER.encode(merged)) > CHUNK_TOKENS:
                chunks.extend(_recursive_split(merged, rest))
            else:
                chunks.append(merged)
            # One-segment overlap
            current = [current[-1]]
            current_tokens = len(TOKENIZER.encode(current[0]))
        current.append(part)
        current_tokens += pt

    if current:
        merged = sep.join(current)
        if len(TOKENIZER.encode(merged)) > CHUNK_TOKENS:
            chunks.extend(_recursive_split(merged, rest))
        else:
            chunks.append(merged)

    return [c.strip() for c in chunks if c.strip()]


def _recursive_split_no_overlap(text: str, separators: list[str]) -> list[str]:
    """Same as _recursive_split but no overlap — used for oversized markdown sections."""
    if not text.strip():
        return []
    if len(TOKENIZER.encode(text)) <= CHUNK_TOKENS:
        return [text]
    if not separators:
        return _hard_split(text)

    sep, rest = separators[0], separators[1:]
    parts = [p for p in text.split(sep) if p.strip()]

    if len(parts) == 1:
        return _recursive_split_no_overlap(text, rest)

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for part in parts:
        pt = len(TOKENIZER.encode(part))
        if current_tokens + pt > CHUNK_TOKENS and current:
            merged = sep.join(current)
            if len(TOKENIZER.encode(merged)) > CHUNK_TOKENS:
                chunks.extend(_recursive_split_no_overlap(merged, rest))
            else:
                chunks.append(merged)
            current, current_tokens = [], 0   # no overlap
        current.append(part)
        current_tokens += pt

    if current:
        merged = sep.join(current)
        if len(TOKENIZER.encode(merged)) > CHUNK_TOKENS:
            chunks.extend(_recursive_split_no_overlap(merged, rest))
        else:
            chunks.append(merged)

    return [c.strip() for c in chunks if c.strip()]


def _hard_split(text: str) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for word in words:
        wt = len(TOKENIZER.encode(word))
        if current_tokens + wt > CHUNK_TOKENS and current:
            chunks.append(" ".join(current))
            current, current_tokens = [], 0
        current.append(word)
        current_tokens += wt
    if current:
        chunks.append(" ".join(current))
    return chunks


# ── Heading extraction ────────────────────────────────────────────────────────

_HEADING_PATTERNS = [
    r'^#{1,6}\s+.{3,80}$',                                # ## Markdown Heading
    r'^(?:Section|Article|Chapter|Part)\s+[\d.]+.*',     # Section 5.2 ...
    r'^\d+\.\s+[A-Z][^\n]{4,60}$',                       # 5. Some Term
    r'^\d+\.\d+\s+[A-Z][^\n]{4,60}$',                    # 5.2 Subsection
    r'^[A-Z][A-Z\s\-]{8,60}$',                            # ALL CAPS HEADING
]


def extract_headings(text: str) -> list[str]:
    """
    Extract section headings from document text.
    Pass raw markdown text (with ## markers) for best results.
    Returns up to 20 unique headings cleaned of markdown syntax.
    """
    headings: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if 5 <= len(line) <= 82 and any(re.match(p, line) for p in _HEADING_PATTERNS):
            # Strip markdown # markers for display
            clean = re.sub(r'^#{1,6}\s+', '', line).strip()
            if clean:
                headings.append(clean)
    return list(dict.fromkeys(headings))[:20]


# ── Public API ────────────────────────────────────────────────────────────────

def parse_and_chunk(path: str | Path) -> tuple[str, list[str]]:
    """
    Returns (raw_or_full_text, chunks).

    For markdown: raw_text is the original file content (## markers intact)
    so that extract_headings() can detect section headings correctly.
    Chunks are section-aware (split on ## boundaries, no overlap).

    For other formats: raw_text is the stripped plain text; chunks use
    recursive splitting with one-segment overlap.
    """
    path = Path(path)
    if path.suffix.lower() == ".md":
        raw = path.read_text(encoding="utf-8", errors="replace")
        chunks = _chunk_markdown(raw)
        return raw, chunks   # return raw so caller can extract ## headings
    else:
        text = parse_file(path)
        chunks = _recursive_split(text.strip(), SEPARATORS)
        return text, chunks
