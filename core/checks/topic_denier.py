import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Map known topics to a list of associated keywords to improve detection coverage
DEFAULT_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "explosives": ["bomb", "tnt", "dynamite", "gunpowder", "c4", "explosive", "detonator", "nitroglycerin"],
    "credential theft": ["phishing", "keylogger", "steal password", "harvest credential", "credential theft", "mimikatz"],
    "malware": ["virus", "trojan", "ransomware", "spyware", "backdoor", "malware", "rootkit", "worm"],
    "hacking": ["hacking", "hack", "exploit", "sql injection", "ddos", "buffer overflow", "cross-site scripting", "xss"]
}

class TopicDenier:
    def __init__(self, model: Any = None):
        self.model = model

    def _get_model(self) -> Any:
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                from app.config import settings
                logger.info(f"Loading SentenceTransformer model: {settings.EMBEDDING_MODEL_NAME}...")
                self.model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers model: {e}")
                raise RuntimeError(f"Failed to load sentence-transformers model: {e}")
        return self.model

    def check_topics(self, text: Any, denied_topics: Optional[List[str]] = None, semantic_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Checks if the text contains references to any of the denied topics.
        Supports both instance-level calls and static-level calls dynamically.
        Returns a list of structured findings.
        """
        # Resolve dynamic arguments (static call vs instance call)
        if isinstance(self, str):
            actual_text = self
            actual_denied_topics = text
            actual_semantic_threshold = denied_topics
            model = None
        else:
            actual_text = text
            actual_denied_topics = denied_topics
            actual_semantic_threshold = semantic_threshold
            model = self.model if hasattr(self, "model") else None

        findings = []
        if not actual_denied_topics:
            return findings

        normalized_text = actual_text.lower()

        # Track topics already matched by keywords to avoid duplicate findings
        matched_topics_by_keyword = set()

        # 1. Keyword / synonym matching
        for topic in actual_denied_topics:
            topic_lower = topic.lower()
            matched = False
            
            # Match topic name itself
            if topic_lower in normalized_text:
                matched = True
            
            # Match associated keywords
            keywords = DEFAULT_TOPIC_KEYWORDS.get(topic_lower, [])
            for kw in keywords:
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, normalized_text):
                    matched = True
                    break

            if matched:
                matched_topics_by_keyword.add(topic)
                findings.append({
                    "topic": topic,
                    "matched": True,
                    "method": "keyword"
                })

        # 2. Semantic matching (if threshold is specified)
        if actual_semantic_threshold is not None:
            # Filter out topics already matched by keyword
            remaining_topics = [t for t in actual_denied_topics if t not in matched_topics_by_keyword]
            if remaining_topics:
                try:
                    # If this was a static call, we load/fetch the model from a default instance
                    if model is None:
                        # Lazy load a temporary model or raise
                        # For static calls in tests, we fallback to default settings-based model
                        from sentence_transformers import SentenceTransformer
                        from app.config import settings
                        model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
                    
                    # Encode texts
                    text_emb = model.encode([actual_text])
                    topic_embs = model.encode(remaining_topics)
                    
                    # Compute cosine similarity
                    from sentence_transformers import util
                    similarities = util.cos_sim(text_emb, topic_embs)[0]
                    
                    for i, topic in enumerate(remaining_topics):
                        score = float(similarities[i])
                        if score >= actual_semantic_threshold:
                            findings.append({
                                "topic": topic,
                                "matched": True,
                                "method": "semantic",
                                "similarity_score": round(score, 4)
                            })
                except Exception as e:
                    logger.error(f"Semantic topic matching failed: {e}", exc_info=True)
                    
        return findings
