from pydantic import BaseModel, Field, field_validator


class PlanTask(BaseModel):

    id: int = Field(
        description="Unique task number starting from 1"
    )

    title: str = Field(
        description="Short technical task title"
    )

    description: str = Field(
        description="Detailed implementation task"
    )

    files_to_modify: list[str] = Field(
        default_factory=list
    )

    files_to_create: list[str] = Field(
        default_factory=list
    )

    dependencies: list[str] = Field(
        default_factory=list
    )

    tests_required: list[str] = Field(
        default_factory=list
    )

    security_considerations: list[str] = Field(
        default_factory=list
    )

    @field_validator(
        "dependencies",
        "files_to_modify",
        "files_to_create",
        "tests_required",
        "security_considerations",
        mode="before",
    )
    @classmethod
    def normalize_list(cls, value):

        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, list):
            return [
                str(item)
                for item in value
            ]

        return [str(value)]


class ImplementationPlan(BaseModel):

    summary: str = Field(
        description="Short summary of the complete implementation"
    )

    tasks: list[PlanTask] = Field(
        description="Ordered implementation tasks"
    )

    testing_strategy: list[str] = Field(
        default_factory=list
    )

    security_strategy: list[str] = Field(
        default_factory=list
    )

    @field_validator(
        "testing_strategy",
        "security_strategy",
        mode="before",
    )
    @classmethod
    def normalize_strategy_list(cls, value):

        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, list):
            return [
                str(item)
                for item in value
            ]

        return [str(value)]