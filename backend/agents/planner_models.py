from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    id: int = Field(description="Unique task number starting from 1")
    title: str = Field(description="Short technical task title")
    description: str = Field(description="Detailed implementation task")
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="Existing repository files that should be modified"
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="New files that should be created"
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Other tasks that must be completed first"
    )
    tests_required: list[str] = Field(
        default_factory=list,
        description="Tests required for this task"
    )
    security_considerations: list[str] = Field(
        default_factory=list,
        description="Security considerations relevant to this task"
    )


class ImplementationPlan(BaseModel):
    summary: str = Field(
        description="Short summary of the complete implementation"
    )
    tasks: list[PlanTask] = Field(
        description="Ordered implementation tasks"
    )
    testing_strategy: list[str] = Field(
        default_factory=list,
        description="Overall testing strategy"
    )
    security_strategy: list[str] = Field(
        default_factory=list,
        description="Overall security considerations"
    )