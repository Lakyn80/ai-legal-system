import inspect
import logging
from threading import Lock

from sentence_transformers import SentenceTransformer


logger = logging.getLogger(__name__)


class SentenceTransformerEmbeddingProvider:
    revision = "sentence_transformer_v1"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._load_error: RuntimeError | None = None
        self._load_lock = Lock()

    @property
    def dimension(self) -> int:
        model = self._get_model()
        value = model.get_sentence_embedding_dimension()
        if value is None:
            return len(self.embed_query("dimension probe"))
        return value

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def _get_model(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            raise self._load_error

        with self._load_lock:
            if self._model is not None:
                return self._model
            if self._load_error is not None:
                raise self._load_error

            try:
                self._model = self._load_model()
                return self._model
            except Exception as exc:
                self._load_error = RuntimeError(
                    f"Failed to load sentence transformer model '{self.model_name}'. "
                    "Configure EMBEDDING_MODEL_NAME or EMBEDDING_MODEL correctly, or switch EMBEDDING_PROVIDER=hash. "
                    f"Original error: {exc}"
                )
                raise self._load_error from exc

    def _load_model(self) -> SentenceTransformer:
        logger.info("Loading sentence transformer model '%s' on CPU", self.model_name)

        init_parameters = inspect.signature(SentenceTransformer.__init__).parameters
        init_kwargs = {"device": "cpu"}

        if "trust_remote_code" in init_parameters:
            init_kwargs["trust_remote_code"] = True
        else:
            logger.warning(
                "Current sentence-transformers build does not support trust_remote_code; loading '%s' without it.",
                self.model_name,
            )

        return SentenceTransformer(self.model_name, **init_kwargs)
