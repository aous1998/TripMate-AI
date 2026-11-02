"""The chat model shared by every agent."""
# -----------------------------------------------------------------------------
# llm.py - creates the Groq chat model ONCE and lets every agent reuse it.
#
# Agents call get_llm() instead of creating their own model. That gives:
#   - one place to choose the model and its settings,
#   - one model object for the whole app (cheaper),
#   - an easy way for tests to swap in a fake model (set_llm).
# -----------------------------------------------------------------------------

import os                              # read GROQ_API_KEY / GROQ_MODEL from the environment

from langchain_groq import ChatGroq    # LangChain's wrapper around Groq's chat API

# The shared model. None until the first get_llm() call creates it.
# (The leading underscore means "private to this file".)
_llm = None


def get_llm():
    # `global` lets this function change the module-level _llm variable.
    global _llm

    # Create the model only the first time; afterwards return the same object.
    if _llm is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            # backend.py calls get_llm() at startup, so a missing key stops the
            # app immediately with this message.
            raise ValueError("GROQ_API_KEY is missing. Please add it to your .env file.")

        # Groq retires models over time; override with GROQ_MODEL in .env if needed.
        _llm = ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),   # default model if not set
            api_key=api_key,
            # A full trip makes ~5 calls; extra retries (which honour Groq's
            # retry-after header) ride out free-tier rate limits.
            max_retries=4,
        )

    return _llm


def set_llm(llm):
    """Replace the shared model, e.g. with a fake one in tests."""
    # Tests call set_llm(FakeLLM(...)); afterwards set_llm(None) resets it.
    global _llm
    _llm = llm
