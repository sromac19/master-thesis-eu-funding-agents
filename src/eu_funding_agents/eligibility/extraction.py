from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol
from urllib.parse import urlparse

import structlog

from eu_funding_agents.config import Settings
from eu_funding_agents.eligibility.schemas import EligibilityExtraction
from eu_funding_agents.metrics import LLM_LATENCY, LLM_REQUESTS, LLM_TOKENS

logger = structlog.get_logger(__name__)

OPENAI_ELIGIBILITY_PROMPT = """You extract formal eligibility rules from one official EU funding document.
Return only criteria explicitly supported by the supplied text. Never decide whether an applicant is
eligible. Never infer missing countries, organisation types, SME status, consortium size, or TRL.
Use only the provided source URL, quote a short exact evidence span for supported criteria, and keep
human_confirmed false. If a potentially relevant criterion is ambiguous, mark it unsupported with a
null expected value and explain what is missing in missing_information.
"""


@dataclass(frozen=True)
class ExtractionUsage:
    provider: str
    model: str
    prompt_version: str
    latency_seconds: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class EligibilityExtractionRun:
    output: EligibilityExtraction
    usage: ExtractionUsage


class OpenAIConfigurationError(ValueError):
    pass


class EligibilityExtractor(Protocol):
    provider: str
    model: str
    prompt_version: str

    async def extract(self, *, document_text: str, source_url: str) -> EligibilityExtraction: ...


class StubEligibilityExtractor:
    provider = "stub"
    model = "deterministic-fixture"
    prompt_version = "eligibility-v1"

    def __init__(self, output: EligibilityExtraction) -> None:
        self._output = output

    async def extract(self, *, document_text: str, source_url: str) -> EligibilityExtraction:
        if not document_text.strip():
            raise ValueError("document_text must not be empty")
        if not source_url.startswith("https://"):
            raise ValueError("source_url must be HTTPS")
        return self._output.model_copy(deep=True)


class OpenAIEligibilityExtractor:
    provider = "openai"
    prompt_version = "eligibility-openai-v1"

    def __init__(
        self,
        client: Any,
        *,
        model: str,
        max_output_tokens: int,
        max_input_chars: int,
    ) -> None:
        self._client = client
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._max_input_chars = max_input_chars

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIEligibilityExtractor:
        if settings.llm_provider.casefold() != "openai":
            raise OpenAIConfigurationError("LLM_PROVIDER must be openai")
        if not settings.llm_model.strip():
            raise OpenAIConfigurationError("LLM_MODEL is required")
        api_key = settings.llm_api_key.get_secret_value()
        if not api_key.strip():
            raise OpenAIConfigurationError("LLM_API_KEY is required")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise OpenAIConfigurationError(
                'Install the optional OpenAI dependency with pip install -e ".[llm]"'
            ) from exc

        client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
        return cls(
            client,
            model=settings.llm_model,
            max_output_tokens=settings.llm_max_tokens,
            max_input_chars=settings.llm_max_input_chars,
        )

    async def extract(self, *, document_text: str, source_url: str) -> EligibilityExtraction:
        return (
            await self.extract_with_usage(document_text=document_text, source_url=source_url)
        ).output

    async def extract_with_usage(
        self, *, document_text: str, source_url: str
    ) -> EligibilityExtractionRun:
        text = document_text.strip()
        if not text:
            raise ValueError("document_text must not be empty")
        if len(text) > self._max_input_chars:
            raise ValueError("document_text exceeds LLM_MAX_INPUT_CHARS")
        parsed_url = urlparse(source_url)
        hostname = (parsed_url.hostname or "").casefold()
        if parsed_url.scheme != "https" or not (
            hostname == "europa.eu" or hostname.endswith(".europa.eu")
        ):
            raise ValueError("source_url must be an official europa.eu HTTPS URL")

        started = perf_counter()
        try:
            response = await self._client.responses.parse(
                model=self.model,
                input=[
                    {"role": "developer", "content": OPENAI_ELIGIBILITY_PROMPT},
                    {
                        "role": "user",
                        "content": f"SOURCE_URL: {source_url}\n\nDOCUMENT_TEXT:\n{text}",
                    },
                ],
                text_format=EligibilityExtraction,
                max_output_tokens=self._max_output_tokens,
                store=False,
            )
            output = response.output_parsed
            if output is None:
                raise RuntimeError("OpenAI response did not contain parsed eligibility output")
            extraction = EligibilityExtraction.model_validate(output)
            for criterion in extraction.criteria:
                if str(criterion.source_url) != source_url:
                    raise RuntimeError("OpenAI response changed the official source URL")
                criterion.human_confirmed = False
        except Exception as exc:
            elapsed = perf_counter() - started
            LLM_REQUESTS.labels(self.provider, self.model, "failure").inc()
            LLM_LATENCY.labels(self.provider, self.model).observe(elapsed)
            logger.warning(
                "llm_eligibility_extraction_failed",
                provider=self.provider,
                model=self.model,
                prompt_version=self.prompt_version,
                duration_seconds=elapsed,
                error_type=type(exc).__name__,
            )
            raise

        elapsed = perf_counter() - started
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        LLM_REQUESTS.labels(self.provider, self.model, "success").inc()
        LLM_LATENCY.labels(self.provider, self.model).observe(elapsed)
        LLM_TOKENS.labels(self.provider, self.model, "input").inc(input_tokens)
        LLM_TOKENS.labels(self.provider, self.model, "output").inc(output_tokens)
        logger.info(
            "llm_eligibility_extraction_completed",
            provider=self.provider,
            model=self.model,
            prompt_version=self.prompt_version,
            duration_seconds=elapsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            criterion_count=len(extraction.criteria),
        )
        return EligibilityExtractionRun(
            output=extraction,
            usage=ExtractionUsage(
                provider=self.provider,
                model=self.model,
                prompt_version=self.prompt_version,
                latency_seconds=elapsed,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        )
