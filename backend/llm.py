import os

from dotenv import load_dotenv
from groq import Groq
from langchain_groq import ChatGroq


load_dotenv()


def get_provider() -> str:
    provider = os.getenv(
        "LLM_PROVIDER",
        "groq",
    ).strip().lower()

    if provider != "groq":
        raise ValueError(
            f"Unsupported LLM provider: {provider}"
        )

    return provider


def get_api_key() -> str:
    get_provider()

    api_key = os.getenv(
        "GROQ_API_KEY"
    )

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is missing from .env"
        )

    return api_key


def get_model() -> str:
    return os.getenv(
        "MODEL",
        "openai/gpt-oss-20b",
    )


def get_llm():
    """
    Return the LangChain Groq client.

    Used by agents that do not require native
    Groq JSON-schema responses.
    """

    return ChatGroq(
        model=get_model(),
        api_key=get_api_key(),
        temperature=0,
        max_retries=3,
    )


def get_groq_client() -> Groq:
    """
    Return the native Groq client.

    Agents that require strict JSON-schema output
    should use this client.
    """

    return Groq(
        api_key=get_api_key()
    )