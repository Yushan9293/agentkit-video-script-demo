from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class OutlineShot(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    镜头序号: int = Field(..., ge=1)
    画面内容: str = Field(..., min_length=1)

    # 大纲阶段：必需（你想要“别太少”，这里就是关键）
    台词要点: List[str] = Field(default_factory=list, min_length=1)

    # 拍摄指导（建议在 prompt 强制输出；这里给默认，避免偶发缺字段炸掉）
    拍摄方式: str = Field(default="", description="如：俯拍固定 / 手持跟随 / 定机位")
    景别: str = Field(default="", description="如：特写 / 中景 / 全景")
    机位: str = Field(default="", description="如：俯拍 / 平视 / 45度")
    运镜: str = Field(default="", description="如：推近 / 拉远 / 横移 / 无")
    时长秒: int = Field(default=6, ge=1)
    字幕: List[str] = Field(default_factory=list)
    音效: str = Field(default="")
    道具: List[str] = Field(default_factory=list)
    转场: str = Field(default="")
    注意事项: List[str] = Field(default_factory=list)


class ScriptOutline(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    主题: str = Field(..., min_length=1)
    风格: str = Field(..., min_length=1)
    格式: str = Field(..., min_length=1)

    一句话梗概: str = Field(..., min_length=1)
    目标受众: str = Field(..., min_length=1)
    核心卖点: List[str] = Field(default_factory=list, min_length=1)

    分镜大纲: List[OutlineShot] = Field(..., min_length=5, max_length=7)


# 如果你目前“一步到位”只输出大纲，其实可以先不启用 VideoScript。
# 但你 video_agent.py 现在用的是 VideoScript.model_validate(data)，所以保留它：
class ScriptInfo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    主题: str = Field(..., min_length=1)
    风格: str = Field(..., min_length=1)
    总时长: str = Field(..., min_length=1)  # 如 "60s"
    BGM: str = Field(..., min_length=1)


class ScriptShot(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    镜头序号: int = Field(..., ge=1)
    画面内容: str = Field(..., min_length=1)

    # 成稿：台词更完整
    台词: List[str] = Field(default_factory=list, min_length=1)

    字幕: List[str] = Field(default_factory=list)
    拍摄方式: str = Field(default="")
    景别: str = Field(default="")
    机位: str = Field(default="")
    运镜: str = Field(default="")
    时长秒: int = Field(default=6, ge=1)
    音效: str = Field(default="")
    道具: List[str] = Field(default_factory=list)
    转场: str = Field(default="")
    注意事项: List[str] = Field(default_factory=list)


class VideoScript(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    脚本基本信息: ScriptInfo
    分镜头脚本: List[ScriptShot] = Field(..., min_length=5, max_length=12)
    结尾引导: str = Field(..., min_length=1)