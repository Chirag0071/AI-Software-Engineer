import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq


load_dotenv()


def get_llm():
    provider = os.getenv(
        "LLM_PROVIDER",
        "groq",
    )

    if provider != "groq":
        raise ValueError(
            f"Unsupported LLM provider: {provider}"
        )

    api_key = os.getenv(
        "GROQ_API_KEY"
    )

    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is missing from .env"
        )

    model = os.getenv(
        "MODEL",
        "openai/gpt-oss-20b",
    )

    return ChatGroq(
        model=model,
        api_key=api_key,
        temperature=0,
        model_kwargs={
            "response_format": {
                "type": "json_object"
            }
        },
    )