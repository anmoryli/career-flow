from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EmailInput(Input):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        return value.lower()


class LoginInput(EmailInput):
    password: str = Field(min_length=12, max_length=128)

    # Password whitespace is significant.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class RegisterInput(LoginInput):
    display_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    code: str = Field(pattern=r"^[0-9]{6}$")


class ThemeInput(Input):
    theme: Literal["light", "dark", "system"]


class ConversationInput(Input):
    title: str = Field(min_length=1, max_length=120)


class MessageInput(Input):
    content: str = Field(min_length=1, max_length=10000)
    request_key: UUID


class MemoryInput(Input):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)
    confirmed: Literal["yes"]


class FieldDefinition(Input):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    label: str = Field(min_length=1, max_length=120)
    type: Literal["text", "textarea", "select", "number", "date", "checkbox"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=50)


class FormBlock(Input):
    type: Literal["form"]
    id: UUID
    fields: list[FieldDefinition] = Field(min_length=1, max_length=20)


class StructuredMessage(Input):
    schema_version: Literal["1.0"]
    message: str = Field(max_length=10000)
    blocks: list[FormBlock] = Field(default_factory=list, max_length=5)
    conversation_state: Literal["active", "waiting_for_user", "completed"]
