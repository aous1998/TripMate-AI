"""The chat model shared by every agent."""

import os

from langchain_groq import ChatGroq

_llm = None


def get_llm():
    global _llm

    if _llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")

        # Groq retires models over time; override with GROQ_MODEL in .env if needed.
        _llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            api_key=api_key,
        )

    return _llm


def set_llm(llm):
    """Replace the shared model, e.g. with a fake one in tests."""
    global _llm
    _llm = llm
