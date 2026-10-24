from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


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


class AccountDeleteInput(Input):
    password: str = Field(min_length=12, max_length=128)
    confirm: Literal["delete"]

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ChangePasswordInput(Input):
    current_password: str = Field(min_length=12, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的新密码不一致")
        return self


class PasswordResetInput(EmailInput):
    code: str = Field(pattern=r"^[0-9]{6}$")
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的新密码不一致")
        return self


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
    type: Literal[
        "text", "textarea", "select", "radio", "multiselect", "number", "date", "checkbox"
    ]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_options(self):
        if self.type in {"select", "radio", "multiselect"}:
            if not self.options or len(set(self.options)) != len(self.options):
                raise ValueError("选择字段需要不重复的选项")
        elif self.options:
            raise ValueError("此字段类型不能提供选项")
        return self


class FormBlock(Input):
    type: Literal["form"]
    id: UUID
    fields: list[FieldDefinition] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_fields(self):
        if len({field.name for field in self.fields}) != len(self.fields):
            raise ValueError("表单字段名称不能重复")
        return self


class StructuredMessage(Input):
    schema_version: Literal["1.0"]
    message: str = Field(max_length=10000)
    blocks: list[FormBlock] = Field(default_factory=list, max_length=5)
    conversation_state: Literal["active", "waiting_for_user", "completed"]

    @model_validator(mode="after")
    def unique_blocks(self):
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("表单块编号不能重复")
        if self.conversation_state == "waiting_for_user" and not self.blocks:
            raise ValueError("等待用户时必须包含表单")
        return self
