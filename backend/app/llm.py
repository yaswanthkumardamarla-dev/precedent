"""All calls to the language model live in this file, so the provider can be swapped in one place."""
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

from app import config

_client = genai.Client(
    api_key=config.GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=90_000),  # milliseconds: give up after 90 seconds
)


class Decision(BaseModel):
    statement: str = Field(
        description="The decision as a short, standalone rule, e.g. 'Use the logging module instead of print.'"
    )
    rationale: str = Field(
        description="Why the team decided this, if a reason was given; otherwise an empty string."
    )
    scope: str = Field(
        description="Files, folders or area it applies to, if stated; otherwise an empty string."
    )
    source_comment_id: int = Field(
        description="The N from the [comment N] tag where the decision is stated or agreed."
    )
    confidence: float = Field(
        description="0 to 1: how sure you are this is a real team decision."
    )


class ExtractionResult(BaseModel):
    decisions: list[Decision]


EXTRACTION_PROMPT = """You read the code review discussion from one pull request and extract the engineering DECISIONS made in it.

A decision is a rule, convention or agreement the team means to apply beyond this single line of code. Examples:
- "We use the logging module instead of print."
- "All new endpoints must have type hints."
- "Don't add new dependencies without discussing them first."

These are NOT decisions:
- One-off fix requests ("rename this variable", "fix the typo")
- Questions, praise, or "LGTM"
- Suggestions that someone rejected, or that are still being argued about

Rules:
- Use only what the comments say. Never invent a decision.
- Write each statement so someone can follow it without reading the thread.
- source_comment_id must be the number from the [comment N] tag where the decision is stated or agreed.
- If there are no decisions, return an empty list.

Discussion:
{transcript}
"""


RETRYABLE = {429, 500, 503, 504}  # rate limit and temporary server problems


def _with_retry(call):
    """Run an API call, waiting and retrying on rate limits or temporary server errors."""
    attempts = 4
    for attempt in range(attempts):
        try:
            return call()
        except errors.APIError as error:
            if error.code not in RETRYABLE or attempt == attempts - 1:
                raise
            wait = 20 * (attempt + 1)
            print(f"    Gemini returned {error.code}, retrying in {wait}s...", flush=True)
            time.sleep(wait)


def extract_decisions(transcript: str) -> list[Decision]:
    response = _with_retry(
        lambda: _client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=EXTRACTION_PROMPT.format(transcript=transcript),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractionResult,
                temperature=0,
            ),
        )
    )
    if response.parsed is None:
        raise RuntimeError(f"Model did not return valid JSON:\n{response.text}")
    return response.parsed.decisions


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Turn decision statements into vectors for storage and search."""
    result = _with_retry(
        lambda: _client.models.embed_content(
            model=config.EMBEDDING_MODEL,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=config.EMBEDDING_DIM,
            ),
        )
    )
    return [embedding.values for embedding in result.embeddings]