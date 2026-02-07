"""Pydantic models for MCP tool inputs/outputs."""

from pydantic import BaseModel, Field


class SaveContextInput(BaseModel):
    project: str = Field(description="Project identifier")
    content: str = Field(description="The context content to save")
    type: str = Field(description="Type: decision, context, note, or code_change")
    title: str | None = Field(default=None, description="Optional title")
    tags: list[str] = Field(default_factory=list, description="Optional tags")


class SearchContextInput(BaseModel):
    query: str = Field(description="Full-text search query")
    project: str = Field(default="default", description="Project to search in")
    limit: int = Field(default=5, description="Max results to return", ge=1, le=50)


class GetProjectSummaryInput(BaseModel):
    project: str = Field(default="default", description="Project identifier")


class LogDecisionInput(BaseModel):
    project: str = Field(description="Project identifier")
    decision: str = Field(description="The decision that was made")
    reasoning: str = Field(default="", description="Why this decision was made")


class GetRecentActivityInput(BaseModel):
    project: str = Field(default="default", description="Project identifier")
    hours: int = Field(default=48, description="How many hours back to look", ge=1, le=720)


class LogSessionInput(BaseModel):
    session_id: str = Field(description="Unique session identifier")
    source: str = Field(description="Source: claude_ai or claude_code")
    project: str = Field(default="default", description="Project identifier")
    summary: str = Field(default="", description="Session summary")
