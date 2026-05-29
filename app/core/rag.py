"""Hybrid (BM25 + semantic) RAG over the SAMA/CMA corpus.

Provider-agnostic: synthesis is delegated to whichever LLMProvider is
configured (Claude for cloud, Ollama for local). Retrieval, query
preprocessing, prompt construction, and out-of-domain guards live here.
"""

from __future__ import annotations

import json
import logging
import pickle
import re
from collections.abc import AsyncIterator
from typing import Any

import numpy as np

from app.config import settings
from app.core.utils import detect_language, extract_article_title
from app.providers import ChatMessage, LLMProvider, get_provider

logger = logging.getLogger(__name__)


SAMA_EN_KEYWORDS = [
    "sama", "finance company", "finance companies", "financing company",
    "licensing fee", "real estate finance", "mortgage", "microfinance",
    "finance control", "monetary authority", "bank", "banking",
]
CMA_EN_KEYWORDS = [
    "cma", "capital market", "securities", "sukuk", "debt instrument",
    "investment fund", "qualified investor", "public offering", "ipo",
    "private placement", "prospectus", "listing", "merger", "acquisition",
    "stock", "shares", "exchange",
]
SAMA_AR_KEYWORDS = [
    "ساما", "شركة التمويل", "شركات التمويل", "رسوم الترخيص",
    "التمويل العقاري", "التمويل الأصغر", "مؤسسة النقد", "البنك المركزي", "تمويل",
]
CMA_AR_KEYWORDS = [
    "مستثمر مؤهل", "المستثمر المؤهل", "هيئة السوق المالية", "هيئة السوق",
    "صكوك", "الصكوك", "طرح عام", "طرح خاص", "نشرة الإصدار",
    "صناديق الاستثمار", "أوراق مالية", "الأوراق المالية", "سوق المال",
    "الاندماج", "الاستحواذ", "الأسهم", "التداول",
]

ARABIC_TO_ENGLISH = {
    "رسوم الترخيص": "licensing fees", "رسوم ترخيص": "licensing fees",
    "شركات التمويل": "finance companies", "شركة التمويل": "finance company",
    "التمويل العقاري": "real estate finance", "التمويل الأصغر": "microfinance",
    "المستثمر المؤهل": "qualified investor", "مستثمر مؤهل": "qualified investor",
    "الصكوك": "sukuk debt instruments", "صكوك": "sukuk debt instruments",
    "أدوات الدين": "debt instruments", "طرح عام": "public offering",
    "طرح خاص": "private placement", "نشرة الإصدار": "prospectus",
    "صناديق الاستثمار": "investment funds", "صندوق استثمار": "investment fund",
    "رأس المال": "capital requirements", "متطلبات رأس المال": "capital requirements",
    "الحد الأدنى": "minimum requirements", "هيئة السوق المالية": "capital market authority CMA",
    "مؤسسة النقد": "SAMA monetary authority", "ساما": "SAMA",
    "الاندماج": "merger", "الاستحواذ": "acquisition", "الأسهم": "shares stocks",
    "الإفصاح": "disclosure", "الحوكمة": "governance", "مجلس الإدارة": "board of directors",
    "تقرير سنوي": "annual report", "القوائم المالية": "financial statements",
    "المراجع الخارجي": "external auditor", "العقوبات": "penalties", "المخالفات": "violations",
    "الترخيص": "license licensing", "التسجيل": "registration", "الإدراج": "listing",
    "السوق الموازية": "parallel market", "الطرح": "offering", "الاكتتاب": "subscription IPO",
}

EXPANSIONS = {
    "sukuk": "debt instruments securities bonds",
    "sukuk issuance": "debt instruments offering securities",
    "debt instruments": "sukuk securities bonds",
    "licensing fee": "license fee financial consideration",
    "licensing fees": "license fee financial consideration",
    "qualified investor": "accredited investor",
    "capital requirements": "minimum capital paid up capital",
    "finance company": "finance companies",
    "microfinance": "micro finance small finance",
    "real estate finance": "mortgage property finance",
    "investment fund": "investment funds",
    "public offering": "IPO offering securities",
    "private placement": "exempt offering",
}

FOLLOW_UP_EN = [
    "yes", "yeah", "sure", "please", "ok", "okay", "simplify", "explain",
    "example", "examples", "scenario", "more details", "elaborate", "clarify",
    "what do you mean", "can you explain", "help me understand",
    "break it down", "in simple terms", "simpler", "easier",
]
FOLLOW_UP_AR = [
    "نعم", "أجل", "طيب", "حسنا", "موافق", "تمام", "وضح", "اشرح",
    "مثال", "أمثلة", "سيناريو", "تفاصيل أكثر", "بسط", "بشكل أبسط",
    "ساعدني أفهم", "ماذا تعني", "اشرح أكثر",
]

OUT_OF_DOMAIN = [
    "weather", "recipe", "cook", "movie", "song", "music", "game", "sport",
    "football", "soccer", "basketball", "joke", "story", "poem", "write me",
    "create a", "translate", "what is the capital", "who is the president",
    "how to code", "python", "javascript", "programming", "health", "medical",
    "doctor", "disease", "travel", "hotel", "flight", "vacation",
    "الطقس", "وصفة", "طبخ", "فيلم", "أغنية", "موسيقى", "لعبة", "رياضة",
    "كرة القدم", "نكتة", "قصة", "قصيدة", "ترجم", "عاصمة", "رئيس",
    "برمجة", "صحة", "طبيب", "سفر",
]


class TadqeeqRAG:
    """Hybrid (BM25 + semantic) RAG over SAMA/CMA regulations.

    Synthesis is delegated to an LLMProvider — same retrieval pipeline runs
    whether the configured provider is Claude (cloud) or Ollama (local).
    """

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider: LLMProvider = provider or get_provider()
        self.documents: list[dict] | None = None
        self.bm25: Any = None
        self.embedder: Any = None
        self.chroma_client: Any = None
        self.collection: Any = None
        self.stats: dict[str, dict[str, int]] = {
            "SAMA": {"en": 0, "ar": 0}, "CMA": {"en": 0, "ar": 0}
        }
        self.ready: bool = False

    def initialize(self) -> None:
        """Load corpus, BM25, embedder, and ChromaDB. Safe to call once at startup."""
        if self.ready:
            return
        logger.info("Loading TadqeeqAI corpus from %s", settings.tadqeeq_data_dir)

        with open(settings.documents_path, encoding="utf-8") as f:
            self.documents = json.load(f)
        for doc in self.documents:
            reg = doc.get("regulator", "CMA")
            lang = doc.get("language", "en")
            if reg in self.stats and lang in self.stats[reg]:
                self.stats[reg][lang] += 1
        logger.info("Loaded %d articles", len(self.documents))

        with open(settings.bm25_path, "rb") as f:
            self.bm25 = pickle.load(f)
        logger.info("Loaded BM25 index")

        from sentence_transformers import SentenceTransformer
        self.embedder = SentenceTransformer(settings.embedding_model)
        logger.info("Loaded embedding model: %s", settings.embedding_model)

        import chromadb
        self.chroma_client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.collection = self.chroma_client.get_collection(settings.chroma_collection)
        logger.info("Connected to ChromaDB collection %r (%d vectors)",
                    settings.chroma_collection, self.collection.count())

        self.ready = True
        logger.info("TadqeeqRAG ready (provider=%s)", self.provider.name)

    def detect_regulator(self, query: str) -> str:
        q_lower = query.lower()
        sama_match = any(kw in q_lower for kw in SAMA_EN_KEYWORDS) or any(kw in query for kw in SAMA_AR_KEYWORDS)
        cma_match = any(kw in q_lower for kw in CMA_EN_KEYWORDS) or any(kw in query for kw in CMA_AR_KEYWORDS)
        if sama_match and cma_match:
            return "BOTH"
        if sama_match:
            return "SAMA"
        if cma_match:
            return "CMA"
        return "BOTH"

    def translate_arabic_query(self, query: str) -> str:
        extras = [en for ar, en in ARABIC_TO_ENGLISH.items() if ar in query]
        return f"{query} {' '.join(extras)}" if extras else query

    def expand_query(self, query: str) -> str:
        q = query.lower()
        expansions = [exp for term, exp in EXPANSIONS.items() if term in q]
        return f"{query} {' '.join(expansions)}" if expansions else query

    def bm25_search(
        self, query: str, regulator: str, language: str, top_k: int = 15, force_english: bool = False
    ) -> list[dict]:
        search_lang = "en" if force_english else language
        tokens = re.findall(r"[؀-ۿ]+|[a-zA-Z]+|\d+", query.lower())
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        results: list[dict] = []
        for idx in np.argsort(scores)[::-1]:
            if scores[idx] <= 0:
                break
            if idx >= len(self.documents):
                continue
            if len(results) >= top_k:
                break
            doc = self.documents[idx]
            if regulator != "BOTH" and doc.get("regulator") != regulator:
                continue
            if doc.get("language") != search_lang:
                continue
            results.append({"doc": doc, "score": float(scores[idx]), "source": "bm25"})
        return results

    def semantic_search(
        self, query: str, regulator: str, language: str, top_k: int = 15, force_english: bool = False
    ) -> list[dict]:
        search_lang = "en" if force_english else language
        embedding = self.embedder.encode([f"query: {query}"]).tolist()
        where = (
            {"language": {"$eq": search_lang}} if regulator == "BOTH"
            else {"$and": [{"language": {"$eq": search_lang}}, {"regulator": {"$eq": regulator}}]}
        )
        try:
            results = self.collection.query(query_embeddings=embedding, n_results=top_k, where=where)
        except Exception as e:
            logger.warning("ChromaDB filtered query failed (%s); retrying without filter.", e)
            try:
                results = self.collection.query(query_embeddings=embedding, n_results=top_k * 2)
            except Exception as e2:
                logger.error("ChromaDB fallback query also failed: %s", e2)
                return []
        output: list[dict] = []
        if results["documents"] and results["documents"][0]:
            for doc_text, meta, dist in zip(
                results["documents"][0], results["metadatas"][0], results["distances"][0], strict=False
            ):
                if regulator != "BOTH" and meta.get("regulator") != regulator:
                    continue
                if meta.get("language") != search_lang:
                    continue
                output.append({
                    "doc": {
                        "text": doc_text,
                        "article": meta.get("article", ""),
                        "document": meta.get("document", ""),
                        "regulator": meta.get("regulator", ""),
                        "language": meta.get("language", ""),
                    },
                    "score": 1 / (1 + dist),
                    "source": "semantic",
                })
        return output[:top_k]

    def hybrid_search(self, query: str, n_results: int = 3) -> tuple[list[dict], str, str]:
        user_language = detect_language(query)
        regulator = self.detect_regulator(query)
        if user_language == "ar":
            english_query = self.translate_arabic_query(query)
            expanded = self.expand_query(english_query)
            bm25_res = self.bm25_search(expanded, regulator, user_language, force_english=True)
            sem_res = self.semantic_search(expanded, regulator, user_language, force_english=True)
        else:
            expanded = self.expand_query(query)
            bm25_res = self.bm25_search(expanded, regulator, user_language)
            sem_res = self.semantic_search(expanded, regulator, user_language)

        doc_scores: dict[str, dict] = {}
        k = 60
        for rank, r in enumerate(bm25_res):
            key = f"{r['doc']['document']}:{r['doc']['article']}"
            entry = doc_scores.setdefault(key, {"doc": r["doc"], "rrf": 0.0, "src": set()})
            entry["rrf"] += 1 / (k + rank + 1)
            entry["src"].add("BM25")
        for rank, r in enumerate(sem_res):
            key = f"{r['doc']['document']}:{r['doc']['article']}"
            entry = doc_scores.setdefault(key, {"doc": r["doc"], "rrf": 0.0, "src": set()})
            entry["rrf"] += 1 / (k + rank + 1)
            entry["src"].add("Semantic")
        sorted_res = sorted(doc_scores.values(), key=lambda x: x["rrf"], reverse=True)
        return [r["doc"] for r in sorted_res[:n_results]], regulator, user_language

    def is_follow_up(self, query: str) -> bool:
        q = query.lower().strip()
        if any(p in q for p in FOLLOW_UP_EN):
            return True
        if any(p in query for p in FOLLOW_UP_AR):
            return True
        return len(query.strip()) < 15 and len(query.split()) <= 3

    def is_out_of_domain(self, query: str) -> bool:
        q = query.lower()
        return any(term in q for term in OUT_OF_DOMAIN)

    def build_system_prompt(
        self,
        docs: list[dict],
        language: str,
        is_follow_up: bool = False,
        conversation_context: list[dict] | None = None,
    ) -> str:
        ctx = "\n\n---\n\n".join(
            f"[Document {i}]\nSource: {d['document']}\nArticle: {d['article']}\nContent:\n{d['text']}"
            for i, d in enumerate(docs, 1)
        )
        conv = ""
        if is_follow_up and conversation_context:
            conv = "\n\nPrevious conversation:\n"
            for msg in conversation_context[-4:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                conv += f"{role}: {msg['content'][:500]}\n"

        if language == "ar":
            instructions = (
                "أنت مساعد قانوني متخصص في الأنظمة المالية السعودية (ساما وهيئة السوق المالية).\n\n"
                "تعليمات مهمة:\n"
                "- اقرأ كل مستند بعناية قبل الإجابة\n"
                "- استخرج المعلومات المطلوبة من المستندات\n"
                "- اذكر **فقط** المادة التي تحتوي فعلياً على الإجابة\n"
                "- مصطلح \"debt instruments\" يعني \"الصكوك\" أو \"أدوات الدين\"\n"
                "- اكتب الأرقام والمبالغ كما هي في المستند\n"
                "- استخدم تنسيق Markdown: **نص** للتأكيد و - للقوائم\n"
                "- إذا لم تجد المعلومة المحددة، قل ذلك بوضوح\n"
                "- كن موجزاً: أجب على السؤال مباشرة\n\n"
                "قاعدة تنسيق صارمة: لا تكتب أبداً بادئات وصفية مثل \"عنوان عريض:\" أو \"Bold heading:\" "
                "قبل أي مفهوم. طبّق التشكيل بصيغة Markdown مباشرة على النص ذاته."
            )
            if is_follow_up:
                instructions += (
                    "\n\nالمستخدم يطلب توضيحاً أو تبسيطاً. اشرح المفهوم بلغة سهلة، "
                    "قدّم مثالاً عملياً إذا طُلب، ووضّح النقاط الغامضة."
                )
        else:
            instructions = (
                "You are a legal assistant specializing in Saudi Arabian financial regulations (SAMA and CMA).\n\n"
                "Important instructions:\n"
                "- Read each document carefully before answering\n"
                "- Extract the relevant information from the documents\n"
                "- Cite **only** the specific article(s) that directly contain the answer\n"
                "- \"Sukuk\" and \"debt instruments\" refer to the same thing\n"
                "- Preserve exact numbers and amounts as written\n"
                "- Use Markdown formatting: **bold** for emphasis and - for lists\n"
                "- If the specific information is not found, say so clearly\n"
                "- Be concise: answer the question directly\n\n"
                "CRITICAL FORMATTING RULE: Never prefix definitions with meta-labels like "
                "\"Bold heading:\" or \"Heading:\". Apply the markdown bold token directly to "
                "the concept itself. Do not name the format — apply it."
            )
            if is_follow_up:
                instructions += (
                    "\n\nThe user is asking for clarification or simplification. Explain in plain "
                    "language, provide a practical example if requested, and clarify unclear points."
                )

        return f"{instructions}{conv}\n\nReference Documents:\n{ctx}"

    def build_out_of_domain_response(self, language: str) -> str:
        if language == "ar":
            return (
                "عذراً، أنا مساعد متخصص في الأنظمة المالية السعودية فقط.\n\n"
                "يمكنني مساعدتك في:\n"
                "- **أنظمة ساما**: شركات التمويل، التمويل العقاري، التمويل الأصغر\n"
                "- **أنظمة هيئة السوق المالية**: الصكوك، صناديق الاستثمار، المستثمر المؤهل\n\n"
                "يرجى طرح سؤال يتعلق بهذه المواضيع."
            )
        return (
            "I apologize, but I am a specialized assistant for Saudi Arabian financial regulations only.\n\n"
            "I can help you with:\n"
            "- **SAMA regulations**: Finance companies, real estate finance, microfinance\n"
            "- **CMA regulations**: Sukuk, investment funds, qualified investors, offerings\n\n"
            "Please ask a question related to these topics."
        )

    def _build_sources(self, docs: list[dict]) -> list[dict]:
        seen: set[str] = set()
        sources: list[dict] = []
        for d in docs:
            article = d.get("article", "")
            if article in seen:
                continue
            seen.add(article)
            sources.append({
                "article": article,
                "document": d.get("document", ""),
                "title": extract_article_title(d.get("text", ""), article),
            })
        return sources

    async def generate_response(
        self, question: str, conversation_context: list[dict] | None = None
    ) -> dict:
        """Run the full RAG pipeline and return {answer, sources, regulator}."""
        language = detect_language(question)
        if self.is_out_of_domain(question):
            return {
                "answer": self.build_out_of_domain_response(language),
                "sources": [],
                "regulator": "NONE",
            }
        is_followup = self.is_follow_up(question)
        docs, regulator, language = self.hybrid_search(question)
        if not docs:
            return {
                "answer": (
                    "No relevant information found."
                    if language == "en"
                    else "لم يتم العثور على معلومات ذات صلة."
                ),
                "sources": [],
                "regulator": regulator,
            }
        system = self.build_system_prompt(docs, language, is_followup, conversation_context)
        messages: list[ChatMessage] = [{"role": "user", "content": question}]
        try:
            answer = await self.provider.generate(
                system=system,
                messages=messages,
                max_tokens=settings.chat_num_predict,
                temperature=0.1,
            )
        except Exception:
            logger.exception("Provider generation failed")
            return {
                "answer": (
                    "An error occurred while generating the response. Please try again."
                    if language == "en"
                    else "حدث خطأ أثناء إنشاء الرد. يرجى المحاولة مرة أخرى."
                ),
                "sources": [],
                "regulator": regulator,
            }
        return {
            "answer": answer.strip(),
            "sources": self._build_sources(docs),
            "regulator": regulator,
        }

    async def stream_response(
        self, question: str, conversation_context: list[dict] | None = None
    ) -> AsyncIterator[dict]:
        """Stream the RAG response as a sequence of events.

        Yields:
            {"type": "meta",  "regulator": str, "sources": list}  (once, first)
            {"type": "token", "text": str}                          (many)
            {"type": "done"}                                        (once, last)
            {"type": "error", "message": str}                       (instead of done)
        """
        language = detect_language(question)
        if self.is_out_of_domain(question):
            yield {"type": "meta", "regulator": "NONE", "sources": []}
            yield {"type": "token", "text": self.build_out_of_domain_response(language)}
            yield {"type": "done"}
            return
        is_followup = self.is_follow_up(question)
        docs, regulator, language = self.hybrid_search(question)
        sources = self._build_sources(docs)
        yield {"type": "meta", "regulator": regulator, "sources": sources}
        if not docs:
            yield {
                "type": "token",
                "text": (
                    "No relevant information found."
                    if language == "en"
                    else "لم يتم العثور على معلومات ذات صلة."
                ),
            }
            yield {"type": "done"}
            return
        system = self.build_system_prompt(docs, language, is_followup, conversation_context)
        messages: list[ChatMessage] = [{"role": "user", "content": question}]
        try:
            async for chunk in self.provider.stream(
                system=system,
                messages=messages,
                max_tokens=settings.chat_num_predict,
                temperature=0.1,
            ):
                yield {"type": "token", "text": chunk}
        except Exception as e:
            logger.exception("Provider stream failed")
            yield {"type": "error", "message": str(e)}
            return
        yield {"type": "done"}


_rag_instance: TadqeeqRAG | None = None


def get_rag() -> TadqeeqRAG:
    """Module-level singleton accessor. Initialized at app startup via lifespan."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = TadqeeqRAG()
    return _rag_instance
