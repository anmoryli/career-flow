"""Strict policy and product actions; no AI-generated executable UI."""

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas import Input


class ModelPrice(Input):
    input_per_million_cny: Decimal = Field(ge=0, le=10000)
    output_per_million_cny: Decimal = Field(ge=0, le=10000)


class ProductPolicy(Input):
    enabled: bool = True
    free_analyses_monthly: int = Field(default=1, ge=1, le=10)
    member_analyses_monthly: int = Field(default=30, ge=1, le=1000)
    member_soft_tokens_monthly: int = Field(default=1000000, ge=10000, le=100000000)
    member_hard_tokens_monthly: int = Field(default=10000000, ge=10000, le=100000000)
    light_model_id: str = Field(default="", max_length=160)
    model_prices: dict[str, ModelPrice] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def budget_order(self):
        if self.member_soft_tokens_monthly > self.member_hard_tokens_monthly:
            raise ValueError("软阈值不能超过安全上限")
        return self


class ExportInput(Input):
    request_key: UUID
    revision: int = Field(ge=1)


class ShareInput(Input):
    request_key: UUID
    confirmed: Literal["yes"]
    fields: list[Literal["scores", "gap_counts", "requirements"]] = Field(
        default_factory=lambda: ["scores", "gap_counts"], min_length=1, max_length=3
    )
    days: int = Field(default=7, ge=1, le=30)


class AdoptionInput(Input):
    request_key: UUID
    operation_id: int = Field(ge=1)
