"""Strict request schemas; unsupported fields never become action parameters."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PairRequest(RequestModel):
    code: str = Field(pattern=r'^\d{6}$', min_length=6, max_length=6)
    device_name: str = Field(min_length=1,max_length=60,pattern=r'^[^\x00-\x1f\x7f]+$')
    device_type: Literal['tv','browser'] = 'tv'


class MessageRequest(RequestModel):
    text: str = Field(min_length=1,max_length=4000)
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{16,80}$')
