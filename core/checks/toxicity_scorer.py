import logging
from typing import Dict, List, Tuple, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

# Hardcoded synthetic training corpus (deterministic and self-contained)
SYNTHETIC_DATA: List[Tuple[str, int]] = [
    # Toxic examples (Label: 1)
    ("I hate you and want to destroy you.", 1),
    ("You are an idiot and completely stupid.", 1),
    ("This is garbage. Shut up and go away.", 1),
    ("Go to hell, you absolute loser.", 1),
    ("You will fail and suffer.", 1),
    ("You suck, this is trash.", 1),
    ("Shut the fuck up.", 1),
    ("You are brainless.", 1),
    ("I will kill you.", 1),
    ("You are useless.", 1),
    ("You are a terrible person.", 1),
    ("This is a stupid question, search it yourself.", 1),
    
    # Clean examples (Label: 0)
    ("Hello, how can I help you today?", 0),
    ("The weather is beautiful and sunny.", 0),
    ("Let's work together to complete this project.", 0),
    ("Can you write a python script to parse JSON?", 0),
    ("I appreciate your assistance on this task.", 0),
    ("Here is the summary of the financial report.", 0),
    ("How do you calculate standard deviation?", 0),
    ("Thank you for the explanation.", 0),
    ("I am doing well, thank you.", 0),
    ("Have a nice day!", 0),
    ("Please explain how standard neural networks function.", 0),
    ("This system is working, but it can be optimized.", 0),
    ("I love reading science fiction books.", 0),
    ("This is a helpful tutorial on database indexes.", 0),
    ("How do I install python on windows?", 0),
    ("The cat is sleeping peacefully on the mat.", 0),
    ("Where is the nearest library or bookstore?", 0),
    ("Can you recommend a good Italian restaurant?", 0),
    ("I am learning how to build clean web applications.", 0),
    ("The sky is blue and clear this morning.", 0),
    ("What is the capital city of France?", 0),
    ("Let's schedule a project review meeting tomorrow.", 0),
    ("The flowers in the garden are blooming.", 0),
    ("Please let me know if you need any assistance.", 0),
    ("This is a clean and friendly sentence.", 0),
    ("We should verify the test results.", 0),
    ("The API server is running smoothly.", 0),
    ("I agree with your helpful suggestion.", 0),
    ("That is a very good and valid point.", 0),
    ("We appreciate your feedback on the product.", 0),
    ("Have a wonderful and great weekend!", 0),
]

class ToxicityScorer:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ToxicityScorer, cls).__new__(cls)
            cls._instance._initialize_model()
            cls._instance.pipeline = None
            cls._instance.use_synthetic = False
        return cls._instance

    def __init__(self, pipeline: Any = None, use_synthetic: Optional[bool] = None):
        if pipeline is not None:
            self.pipeline = pipeline
        if use_synthetic is not None:
            self.use_synthetic = use_synthetic

    def _initialize_model(self) -> None:
        """Trains the vectorizer and classifier at startup on the synthetic dataset."""
        logger.info("Initializing synthetic toxicity model...")
        texts = [item[0] for item in SYNTHETIC_DATA]
        labels = [item[1] for item in SYNTHETIC_DATA]

        self.vectorizer = TfidfVectorizer(
            analyzer="word", 
            ngram_range=(1, 1), 
            lowercase=True,
            stop_words="english"
        )
        self.classifier = LogisticRegression(
            random_state=42, 
            solver="liblinear",
            C=100.0
        )

        X = self.vectorizer.fit_transform(texts)
        self.classifier.fit(X, labels)
        logger.info("Synthetic toxicity model trained successfully.")

    def _get_pipeline(self) -> Any:
        if self.pipeline is None:
            from app.config import settings
            if settings.USE_HF_TOXICITY:
                try:
                    from transformers import pipeline
                    logger.info(f"Loading Hugging Face text-classification pipeline: {settings.TOXICITY_MODEL_NAME}...")
                    self.pipeline = pipeline(
                        "text-classification",
                        model=settings.TOXICITY_MODEL_NAME,
                        device="cpu"
                    )
                except Exception as e:
                    logger.warning(f"Could not load Hugging Face pipeline '{settings.TOXICITY_MODEL_NAME}', fallback to synthetic TF-IDF: {e}")
                    self.pipeline = "FALLBACK"
            else:
                self.pipeline = "FALLBACK"
        return self.pipeline

    def _score_synthetic(self, text: str) -> float:
        features = self.vectorizer.transform([text])
        prob_toxic = self.classifier.predict_proba(features)[0][1]
        return float(prob_toxic)

    def _normalize_output(self, results: Any) -> float:
        """
        Normalizes standard Hugging Face text-classification outputs to score [0.0, 1.0].
        """
        if not results:
            return 0.0

        if isinstance(results[0], list):
            results = results[0]

        toxic_score = 0.0
        has_explicit_toxic = False

        for item in results:
            lbl = item.get("label", "").lower()
            val = float(item.get("score", 0.0))

            # Check clean/neutral/inverted labels first to avoid 'non_hate' matching 'hate' via substring
            if any(c in lbl for c in ["non-hate", "non_hate", "non-toxic", "non_toxic", "positive", "label_0", "neutral", "clean"]):
                clean_score = val
                if not has_explicit_toxic:
                    toxic_score = max(toxic_score, 1.0 - clean_score)
            elif any(t in lbl for t in ["hate", "toxic", "insult", "threat", "obscene", "negative", "label_1", "naughty"]):
                has_explicit_toxic = True
                if val > toxic_score:
                    toxic_score = val

        return toxic_score

    def score(self, text: str) -> float:
        """
        Calculates toxicity score between 0.0 and 1.0.
        Uses the production HF model if available and enabled; otherwise falls back to TF-IDF.
        """
        if not text.strip():
            return 0.0
            
        if self.use_synthetic:
            return self._score_synthetic(text)

        pipe = self._get_pipeline()
        if pipe is not None and pipe != "FALLBACK":
            try:
                results = pipe(text)
                return self._normalize_output(results)
            except Exception as e:
                logger.warning(f"HF toxicity inference failed, using synthetic model: {e}")
                
        return self._score_synthetic(text)
