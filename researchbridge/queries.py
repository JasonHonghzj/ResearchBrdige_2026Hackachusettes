"""Translate known built-in queries while preserving user-authored research goals."""
import unicodedata

from researchbridge.discovery import CUES, METHODS


# Retain old examples so links and sessions created by earlier versions translate.
LEGACY_QUERIES = {
    "medication": {"labels": ("用藥素養", "medication literacy", "alfabetización sobre medicamentos"), "query": "medication literacy chatbot", "aliases": ("藥物素養",)},
    "care": {"labels": ("照護銜接", "care transition nursing", "transición de cuidados"), "query": "care transition nursing community discharge", "aliases": ("Care transition", "transición asistencial")},
    "privacy": {"labels": ("大型語言模型 隱私", "large language models privacy", "modelos de lenguaje privacidad"), "query": "large language models LLM privacy preserving", "aliases": ("LLM privacy",)},
    "protein": {"labels": ("蛋白質", "protein structure", "proteínas"), "query": "protein structure sequence", "aliases": ()},
}


def _normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def built_in_query(text):
    normalized = _normalize(text)
    for entry in (*LEGACY_QUERIES.values(), *METHODS.values(), *CUES.values()):
        forms = (*entry["labels"], entry["query"], *entry.get("aliases", ()))
        if any(normalized == _normalize(form) for form in forms):
            return entry
    return None


def localize_query(text, language):
    entry = built_in_query(text)
    return entry["labels"][("zh", "en", "es").index(language)] if entry else text


def canonical_query(text):
    """Use the same retrieval query in every language for a built-in concept."""
    entry = built_in_query(text)
    return entry["query"] if entry else text
