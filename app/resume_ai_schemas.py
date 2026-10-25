"""Validated requests and output for a single resume text rewrite."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas import Input

RewriteMode = Literal["optimize", "expand", "generate", "professional", "concise"]


class ResumeAIQuote(Input):
    request_key: UUID
    revision: int = Field(gt=0)
    mode: RewriteMode
    path: str = Field(
        pattern=r"^(summary|experiences\.[0-9]{1,2}\.bullets\.[0-9]{1,2}|projects\.[0-9]{1,2}\.description|education\.[0-9]{1,2}\.detail)$"
    )


class ResumeAIOutput(Input):
    proposed: str = Field(min_length=1, max_length=3000)
    reason: str = Field(min_length=1, max_length=500)
