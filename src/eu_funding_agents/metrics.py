from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "eu_funding_http_requests_total",
    "HTTP requests handled by the API",
    ("method", "route", "status"),
)
HTTP_LATENCY = Histogram(
    "eu_funding_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ("method", "route"),
)
LLM_REQUESTS = Counter(
    "eu_funding_llm_requests_total",
    "LLM requests completed by provider, model, and status",
    ("provider", "model", "status"),
)
LLM_LATENCY = Histogram(
    "eu_funding_llm_request_duration_seconds",
    "LLM request latency in seconds",
    ("provider", "model"),
)
LLM_TOKENS = Counter(
    "eu_funding_llm_tokens_total",
    "LLM tokens reported by the provider",
    ("provider", "model", "direction"),
)
