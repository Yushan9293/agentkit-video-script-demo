import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional, List

from veadk import Agent, Runner
from schemas.script_schema import ScriptOutline  # ✅ 大纲 schema

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "video_prompt.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_agent(system_prompt: str) -> Agent:
    return Agent(
        name="短视频脚本Agent",
        description="输出短视频分镜大纲（严格JSON，中文字段）。",
        instructions=system_prompt,
        tools=[],
    )


def _to_text(result: Any) -> str:
    if result is None:
        return ""
    for attr in ("final_output", "output_text", "text", "content", "output"):
        v = getattr(result, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if isinstance(result, dict):
        for k in ("final_output", "output_text", "text", "content", "output"):
            v = result.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return str(result).strip()


def _resolve_maybe_coroutine(x: Any) -> Any:
    if not asyncio.iscoroutine(x):
        return x
    try:
        asyncio.get_running_loop()
        has_loop = True
    except RuntimeError:
        has_loop = False

    if not has_loop:
        return asyncio.run(x)

    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(x)).result()


def _extract_first_json_object(text: str) -> Optional[str]:
    """按 { } 计数提取第一个 JSON 对象，避免模型输出夹杂文本导致解析失败。"""
    if not text:
        return None
    s = text.strip()
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    json_str = raw if (raw.startswith("{") and raw.endswith("}")) else (_extract_first_json_object(raw) or "")
    if not json_str:
        raise RuntimeError(f"模型输出中没有找到JSON对象。raw_preview={raw[:300]!r}")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "模型输出不是合法 JSON（必须双引号）。\n"
            f"json_preview={json_str[:300]!r}\n"
            f"raw_preview={raw[:300]!r}"
        ) from e

    if not isinstance(data, dict):
        raise RuntimeError(f"JSON 顶层必须是对象(dict)，但得到的是 {type(data)}")

    return data


def _call_model(user_content: str) -> str:
    system_prompt = _load_prompt()
    agent = _build_agent(system_prompt)
    runner = Runner(agent=agent)

    # 注意：容器里如果没有 VeADK 配置/密钥，这里会直接报错。
    # 我们把异常抛出，让上层决定是否 fallback 到模板输出。
    result = runner.run(messages=user_content, user_id="local")
    result = _resolve_maybe_coroutine(result)
    return _to_text(result)


def _safe_list_str(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    return []


def _fill_outline_defaults(data: Dict[str, Any], topic: str, style: str, fmt: str) -> Dict[str, Any]:
    """
    ✅ 最小兜底：让模型偶尔缺字段也不会直接校验爆炸
    你后续想更“丰富”，主要靠 prompt，而不是在这里硬修复。
    """
    out = dict(data)

    out.setdefault("主题", topic)
    out.setdefault("风格", style)
    out.setdefault("格式", fmt)
    out.setdefault("一句话梗概", f"{topic}｜{style}｜{fmt}")
    out.setdefault("目标受众", "想要快速上手的人群")
    out.setdefault("核心卖点", ["简单易做", "低卡饱腹", "适合日常坚持"])

    shots = out.get("分镜大纲")
    if not isinstance(shots, list):
        shots = []

    fixed = []
    for idx, s in enumerate(shots, start=1):
        if not isinstance(s, dict):
            continue
        s2 = dict(s)
        s2.setdefault("镜头序号", idx)
        s2.setdefault("画面内容", "补充画面内容")

        # 必须数组：台词要点
        if "台词要点" not in s2:
            if "台词" in s2:
                s2["台词要点"] = _safe_list_str(s2.get("台词"))
            else:
                s2["台词要点"] = ["补充台词要点"]
        else:
            s2["台词要点"] = _safe_list_str(s2.get("台词要点")) or ["补充台词要点"]

        fixed.append(s2)

    # 5~7 个镜头（与 prompt / schema 对齐）
    fixed = fixed[:7]
    while len(fixed) < 5:
        fixed.append({"镜头序号": len(fixed) + 1, "画面内容": "补充镜头", "台词要点": ["补充台词要点"]})

    out["分镜大纲"] = fixed
    return out


# ✅ 对外函数：单步输出“大纲”
def generate_outline(topic: str, style: str, fmt: str = "分镜") -> ScriptOutline:
    user_content = f"topic: {topic}\nstyle: {style}\nformat: {fmt}"

    # ✅ 先尝试走模型；如果容器没配置 key/配置文件，直接用模板兜底，保证 demo 可跑。
    try:
        text = _call_model(user_content)
        data = _parse_json_from_text(text)
        data = _fill_outline_defaults(data, topic=topic, style=style, fmt=fmt)
        return ScriptOutline.model_validate(data)
    except Exception:
        return _template_outline(topic=topic, style=style, fmt=fmt)


def _template_outline(topic: str, style: str, fmt: str) -> ScriptOutline:
    """无模型/无配置时的最小可运行 demo：输出 6 镜头分镜大纲。"""
    hook = f"{topic}，3分钟搞定！"
    data: Dict[str, Any] = {
        "主题": topic,
        "风格": style,
        "格式": fmt,
        "一句话梗概": f"用{style}口吻，快速输出{topic}的短视频分镜大纲。",
        "目标受众": "想快速获取结构化短视频脚本的人",
        "核心卖点": ["结构清晰", "镜头可拍", "台词有要点"],
        "分镜大纲": [
            {
                "镜头序号": 1,
                "画面内容": f"开场特写：成品/关键画面一闪而过，屏幕大字：{hook}",
                "台词要点": ["先给结果", f"今天教你：{topic}"],
                "拍摄方式": "快切+大字幕",
                "景别": "特写",
                "机位": "平视",
                "运镜": "推近",
                "时长秒": 5,
                "字幕": [hook, f"主题：{topic}"],
                "音效": "开场提示音",
                "道具": [],
                "转场": "跳剪",
                "注意事项": ["第一秒抓眼"],
            },
            {
                "镜头序号": 2,
                "画面内容": "中景：展示材料/工具，逐个指给镜头看",
                "台词要点": ["准备材料/工具", "可替换方案"],
                "拍摄方式": "定机位",
                "景别": "中景",
                "机位": "45度",
                "运镜": "无",
                "时长秒": 7,
                "字幕": ["准备这些就够了"],
                "音效": "轻快BGM",
                "道具": ["主要材料/道具"],
                "转场": "切镜",
                "注意事项": ["材料摆整齐"],
            },
            {
                "镜头序号": 3,
                "画面内容": "俯拍特写：步骤1，关键动作放大（例如倒/切/拌/加热）",
                "台词要点": ["步骤1要点", "别踩坑"],
                "拍摄方式": "俯拍固定",
                "景别": "特写",
                "机位": "俯拍",
                "运镜": "无",
                "时长秒": 8,
                "字幕": ["步骤1：关键点写这里"],
                "音效": "操作音",
                "道具": [],
                "转场": "跳剪",
                "注意事项": ["把关键动作拍清楚"],
            },
            {
                "镜头序号": 4,
                "画面内容": "俯拍特写：步骤2，展示变化过程（颜色/状态/浓稠度等）",
                "台词要点": ["步骤2要点", "时间/火候/比例"],
                "拍摄方式": "俯拍固定",
                "景别": "特写",
                "机位": "俯拍",
                "运镜": "轻微横移",
                "时长秒": 9,
                "字幕": ["步骤2：注意火候/时间"],
                "音效": "轻快BGM",
                "道具": [],
                "转场": "切镜",
                "注意事项": ["镜头别抖"],
            },
            {
                "镜头序号": 5,
                "画面内容": "成品特写：装盘/摆盘，撒料或收尾动作",
                "台词要点": ["成品展示", "口感/效果描述"],
                "拍摄方式": "特写推近",
                "景别": "特写",
                "机位": "平视",
                "运镜": "推近",
                "时长秒": 7,
                "字幕": ["完成！看这个质感"],
                "音效": "咔嚓/环境音",
                "道具": ["餐具"],
                "转场": "慢切",
                "注意事项": ["光线要干净"],
            },
            {
                "镜头序号": 6,
                "画面内容": "试吃/总结：人物出镜或手部试吃，最后给行动引导",
                "台词要点": ["总结一句", "点赞收藏关注"],
                "拍摄方式": "人物半身/手持",
                "景别": "中近景",
                "机位": "平视",
                "运镜": "轻微跟随",
                "时长秒": 8,
                "字幕": ["想要完整版？评论区见"],
                "音效": "收尾提示音",
                "道具": [],
                "转场": "无",
                "注意事项": ["结尾给明确引导"],
            },
        ],
    }
    data = _fill_outline_defaults(data, topic=topic, style=style, fmt=fmt)
    return ScriptOutline.model_validate(data)


# ✅ simple_agent.py 入口需要的函数名（保持对外 API 稳定）
def generate_script(topic: str, style: str, fmt: str = "分镜") -> ScriptOutline:
    return generate_outline(topic=topic, style=style, fmt=fmt)