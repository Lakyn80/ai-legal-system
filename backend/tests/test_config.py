from app.core.config import Settings


def test_settings_accept_embedding_model_name_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "Alibaba-NLP/gte-multilingual-base")
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.embedding_model == "Alibaba-NLP/gte-multilingual-base"


def test_settings_keep_backward_compatibility_for_embedding_model_env(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL_NAME", raising=False)
    monkeypatch.setenv("EMBEDDING_MODEL", "legacy-model")

    settings = Settings(_env_file=None)

    assert settings.embedding_model == "legacy-model"


def test_settings_normalize_provider_alias_and_default_qdrant_alias(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.delenv("QDRANT_COLLECTION_ALIAS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "sentence_transformer"
    assert settings.qdrant_collection_alias_name == "legal_documents_active"


def test_settings_keep_exact_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REDIS_ENABLED", raising=False)
    monkeypatch.delenv("EXACT_CACHE_ENABLED", raising=False)
    monkeypatch.delenv("SEMANTIC_CACHE_ENABLED", raising=False)

    settings = Settings(_env_file=None)

    assert settings.redis_enabled is False
    assert settings.exact_cache_enabled is False
    assert settings.semantic_cache_enabled is False
    assert settings.redis_url == "redis://redis:6379/0"
