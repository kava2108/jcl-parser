from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

ParamValue = Union[str, List[Any], Dict[str, Any]]


class DDStatement(BaseModel):
    type: Literal["DD"] = "DD"
    name: Optional[str] = None
    params: Dict[str, ParamValue]
    concatenated: bool = False
    instream: Optional[List[str]] = None


class ExecStep(BaseModel):
    type: Literal["EXEC"] = "EXEC"
    name: str
    params: Dict[str, ParamValue]
    dds: List[DDStatement] = Field(default_factory=list)


class JobAST(BaseModel):
    type: Literal["JOB"] = "JOB"
    name: Optional[str] = None
    params: Dict[str, ParamValue]
    steps: List[ExecStep] = Field(default_factory=list)


def to_model(ast_dict: Dict[str, Any]) -> JobAST:
    return JobAST.model_validate(ast_dict)
