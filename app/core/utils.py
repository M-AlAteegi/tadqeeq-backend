import re

_ARTICLE_TITLE_RE = re.compile(r"[\s\.\-—–:]+(.+)$")


def extract_article_title(text: str, article: str) -> str:
    """Pull the article title out of the document text when present.

    Articles typically open with their title on the first non-empty line
    (e.g., "Article 41 — Profit Forecasts"). Returns empty string when the
    source PDF didn't include a title (~32% of corpus — a SAMA/CMA
    publication artifact, not an ingestion bug).
    """
    if not text or not article:
        return ""
    first_line = text.split("\n", 1)[0].strip()
    first_line = re.sub(r"^#+\s*", "", first_line).strip()
    if not first_line.lower().startswith(article.lower()):
        return ""
    tail = first_line[len(article) :]
    m = _ARTICLE_TITLE_RE.match(tail)
    if not m:
        return ""
    title = m.group(1).strip()
    title = re.sub(r"[\.:;,—–\-]+$", "", title).strip()
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title


def detect_language(text: str) -> str:
    arabic_chars = len(re.findall(r"[؀-ۿ]", text))
    return "ar" if arabic_chars > len(text) * 0.3 else "en"
