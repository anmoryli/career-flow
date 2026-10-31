import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    username: str = Field(default="", max_length=254)
    sender: str = Field(min_length=3, max_length=254)
    use_tls: bool = True
    use_ssl: bool = False
    enabled: bool = True

    @field_validator("host")
    @classmethod
    def safe_host(cls, value):
        if any(ch in value for ch in "/:@?#\\ "):
            raise ValueError("Only a DNS name or IP address is allowed")
        return value

    @model_validator(mode="after")
    def one_transport(self):
        if self.use_tls and self.use_ssl:
            raise ValueError("Choose either STARTTLS or implicit SSL")
        return self


def _https_model_endpoint(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
    ):
        raise ValueError("The model endpoint must use HTTPS without userinfo or fragments")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("The model endpoint must not target a local service")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("The model endpoint must use a public address")
    path = parsed.path.rstrip("/")
    # The OpenAI SDK appends /chat/completions itself. Accept pasted full
    # completion URLs, but store and display the corresponding API base URL.
    if path.endswith("/chat/completions"):
        path = path[: -len("/chat/completions")]
    # These public providers expose their compatible API under /v1 even when
    # their documentation gives the bare host as the base address.
    if not path and host in {"api.deepseek.com", "api.siliconflow.cn"}:
        path = "/v1"
    return parsed._replace(path=path).geturl().rstrip("/")


class ModelEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider: str = Field(min_length=1, max_length=60)
    model_id: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=12, max_length=500)

    @field_validator("base_url")
    @classmethod
    def https_endpoint(cls, value):
        return _https_model_endpoint(value)


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    models: list[ModelEndpoint] = Field(min_length=3, max_length=3)
    # Accept the retired setting in previously published configurations; it is unused.
    tokens_per_credit: int | None = Field(default=None, ge=1, le=1000000)
    enabled: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, value):
        if not isinstance(value, dict) or "models" in value:
            return value
        provider = value.get("provider", "")
        base_url = value.get("base_url", "")
        identifiers = [value.get("model_id", ""), *value.get("fallback_model_ids", [])]
        if len(identifiers) == 3:
            value = dict(value)
            value["models"] = [
                {"provider": provider, "model_id": model_id, "base_url": base_url}
                for model_id in identifiers
            ]
            value.pop("provider", None)
            value.pop("model_id", None)
            value.pop("fallback_model_ids", None)
            value.pop("base_url", None)
        return value

    @model_validator(mode="after")
    def valid_profiles(self):
        ids = [item.model_id for item in self.models]
        if len(set(ids)) != len(ids):
            raise ValueError("All three model IDs must be unique")
        return self


class DiagnosisPromptSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    instructions: str = Field(min_length=10, max_length=12000)
    output_schema: str = Field(pattern=r"^diagnosis-v1$")
    variables: list[str] = Field(min_length=1, max_length=10)
    enabled: bool = True

    @field_validator("variables")
    @classmethod
    def known_variables(cls, value):
        allowed = {"document", "jd", "answers", "kind", "rounds"}
        if set(value) != allowed or len(value) != len(allowed):
            raise ValueError("Diagnosis variables must match the server input schema")
        return value


ModelPurpose = Literal[
    "resume_optimize",
    "jd_parse",
    "resume_extract",
    "analysis",
    "followup",
    "report",
    "conversation_summary",
    "long_term_memory",
    "structured_ui",
    "ocr_correction",
    "prompt_test",
]


class ModelRouteSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    routes: dict[ModelPurpose, str] = Field(default_factory=dict, max_length=11)
    enabled: bool = True

    @field_validator("routes")
    @classmethod
    def valid_ids(cls, value):
        if any(not model_id or len(model_id) > 120 for model_id in value.values()):
            raise ValueError("Model IDs must be 1 to 120 characters")
        return value


class ConfigDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=100)
    settings: dict
    secret: str = Field(default="", max_length=8192)


class ConfigPublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool


class ConfigRollbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision_id: int = Field(gt=0)
    confirm: bool
