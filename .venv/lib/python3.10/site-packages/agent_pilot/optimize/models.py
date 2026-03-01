from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

from agent_pilot.models import Variable


class OptimizeState(Enum):
    CREATED = 1
    RUNNING = 2
    SUCCESS = 3
    FAILED = 4


class OptimizeProgress(BaseModel):
    percent: float = Field(alias="ProgressPercent")
    total_cnt: int = Field(alias="TotalCnt")
    better_cnt: int = Field(alias="BetterCnt")
    worse_cnt: int = Field(alias="WorseCnt")
    unchanged_cnt: int = Field(alias="UnchangedCnt")
    init_fullscore_cnt: int = Field(alias="InitFullscoreCnt")
    fullscore_cnt_list: List[int] = Field(alias="FullscoreCntList")
    init_average_score: float = Field(alias="InitAverageScore")
    average_score_list: List[float] = Field(alias="AverageScoreList")
    optimize_token_consumption: int = Field(alias="OptimizeTokenConsumption")
    optimal_prompt: Optional[str] = Field(default=None, alias="OptimalPrompt")


class OptimizeJobInfoPayload(BaseModel):
    JobId: str
    Version: str
    State: int
    CreatedTime: str
    UpdatedTime: str
    OptimizedVersion: Optional[str] = None


class OptimizeServiceStartOptimizeResult(BaseModel):
    TaskId: str
    Version: str
    OptimizeJobId: str


class OptimizeServiceStartOptimizeReq(BaseModel):
    TaskId: str
    Version: str


class OptimizeServiceProgressReq(BaseModel):
    OptimizeJobId: str


class OptimizeServiceProgressResult(BaseModel):
    JobInfo: OptimizeJobInfoPayload
    Progress: Optional[OptimizeProgress] = None


class OptimizeJobInfo(BaseModel):
    job_id: str
    state: OptimizeState
    progress: Optional[OptimizeProgress] = None
    optimized_version: Optional[str] = None


class OptimizeDataRecord(BaseModel):
    record_id: str
    variables: Optional[List[Variable]] = None
    model_answer: Optional[str] = None
    ref_answer: Optional[str] = None
    score: Optional[int] = None
    analysis: Optional[str] = None
    confidence: Optional[float] = None


class OptimizeResult(BaseModel):
    records: List[OptimizeDataRecord]
    prompt: str
    metric: str
    avg_score: float


class OptimizeReport(BaseModel):
    base: OptimizeResult
    opt: OptimizeResult
