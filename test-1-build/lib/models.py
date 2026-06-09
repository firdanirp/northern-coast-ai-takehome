from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    text: str


class LeadInput(BaseModel):
    lead_id: str
    channel: str = "unknown"
    conversation: list[ConversationTurn] = Field(default_factory=list)


class ExtractedSignals(BaseModel):
    """Structured output of the LLM extraction step."""
    volume_fcl_per_month: float | None    # None if not mentioned
    license_status: Literal["valid", "in_process", "none", "unclear"]
    product_fit: bool                      # True if a portfolio brand is named
    years_importing: int | None           # None if not mentioned
    retail_accounts: int | None           # None if not mentioned
    existing_brands: int | None           # Count of brands they currently import
    is_consumer: bool                     # True if clearly a retail/personal request
    raw_channel: str                      # Pass-through from input


class ScoredOutput(BaseModel):
    lead_id: str
    score: int
    tier: Literal["Hot", "Warm", "Cold"]
    routing: Literal["kam_handoff", "nurture_pool", "auto_archive"]
    reasoning: str
