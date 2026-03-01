import json
import logging
import os
import traceback
import uuid
from datetime import datetime
from typing import Any, Dict, List

from agentkit.apps import AgentkitSimpleApp
from agents.video_agent import generate_script  # 生成 outline（大纲/分镜大纲）

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = AgentkitSimpleApp()

DRAFT_DIR = os.environ.get("DRAFT_DIR", "/tmp/agent_drafts")
os.makedirs(DRAFT_DIR, exist_ok=True)


# -------------------------
# helpers: parsing + io
# -------------------------
def _parse_kv_lines(prompt: str) -> Dict[str, str]:
    res: Dict[str, str] = {}
    if not prompt:
        return res
    lines = [l.strip() for l in prompt.splitlines() if l.strip()]
    for line in lines:
        if ":" in line:
            k, v = line.split(":", 1)
        elif "：" in line:
            k, v = line.split("：", 1)
        else:
            continue
        res[k.strip()] = v.strip()
    return res


def _normalize_step(step_raw: str) -> str:
    """
    支持：outline / revise / final
    兼容中文：梗概/大纲/概要/提纲；修改/迭代；终稿/完整版
    """
    s = (step_raw or "").strip().lower()
    if s in ("", "outline", "draft", "summary", "梗概", "大纲", "概要", "提纲"):
        return "outline"
    if s in ("revise", "edit", "update", "修改", "迭代", "调整"):
        return "revise"
    if s in ("final", "full", "finalize", "终稿", "完整版", "完整", "完整内容"):
        return "final"
    return "outline"


def _normalize_detail(detail_raw: str) -> str:
    """
    detail 控制 outline/revise 的返回详细度：
    - short（默认）：返回梗概版
    - full：返回完整 outline
    """
    s = (detail_raw or "").strip().lower()
    if s in ("full", "all", "true", "1", "完整", "全量"):
        return "full"
    return "short"


def _to_plain_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(by_alias=True, exclude_none=False)
    if hasattr(obj, "dict"):
        return obj.dict()
    try:
        return json.loads(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return {"value": str(obj)}


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return x if isinstance(x, str) else str(x)


def _draft_path(draft_id: str) -> str:
    safe = "".join([c for c in draft_id if c.isalnum()])[:32]
    return os.path.join(DRAFT_DIR, f"{safe}.json")


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _save_draft_bundle(draft_id: str, bundle: Dict[str, Any]) -> None:
    path = _draft_path(draft_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False)


def _load_draft_bundle(draft_id: str) -> Dict[str, Any]:
    path = _draft_path(draft_id)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------
# outline structure helpers
# -------------------------
def _extract_shots(outline: Dict[str, Any]) -> List[Dict[str, Any]]:
    shots = outline.get("分镜") or outline.get("镜头") or outline.get("shots") or outline.get("scenes") or []
    if not isinstance(shots, list):
        return []
    return [s for s in shots if isinstance(s, dict)]


def _set_shots(outline: Dict[str, Any], shots: List[Dict[str, Any]]) -> None:
    outline["分镜"] = shots


def _find_shot_index(shots: List[Dict[str, Any]], idx_1_based: int) -> int:
    if not shots:
        return -1
    if 1 <= idx_1_based <= len(shots):
        return idx_1_based - 1
    keys = ["镜头序号", "序号", "编号", "shot_id", "index"]
    target = str(idx_1_based)
    for i, s in enumerate(shots):
        for k in keys:
            if k in s and str(s.get(k)) == target:
                return i
    return -1


# -------------------------
# presentation: make outline SHORT
# -------------------------
def _shots_brief(shots: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    brief = []
    for idx, s in enumerate(shots[:limit], start=1):
        dur = _safe_str(s.get("时长") or s.get("duration") or "")
        visual = _safe_str(s.get("画面内容") or s.get("画面") or s.get("visual") or "")
        dialog = _safe_str(s.get("台词") or s.get("台词要点") or s.get("dialog") or "")
        subtitle = _safe_str(s.get("字幕") or s.get("subtitle") or "")
        brief.append(
            {
                "镜头": idx,
                "时长": dur,
                "画面一句话": visual[:60] + ("…" if len(visual) > 60 else ""),
                "台词一句话": dialog[:60] + ("…" if len(dialog) > 60 else ""),
                "字幕": subtitle[:40] + ("…" if len(subtitle) > 40 else ""),
            }
        )
    return brief


def _make_outline_summary(outline: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ 梗概版 outline：不输出超长分镜，但要让人“看得懂故事线、能修改”
    """
    topic = _safe_str(outline.get("主题") or outline.get("topic") or "")
    style = _safe_str(outline.get("风格") or outline.get("style") or "")
    fmt = _safe_str(outline.get("格式") or outline.get("format") or "分镜")
    one_liner = _safe_str(outline.get("一句话梗概") or outline.get("summary") or "")
    audience = _safe_str(outline.get("目标受众") or outline.get("受众") or outline.get("audience") or "")
    points = outline.get("核心卖点") or outline.get("卖点") or outline.get("points") or []
    if not isinstance(points, list):
        points = [str(points)] if points else []

    shots = _extract_shots(outline)

    def pick(i: int, key_candidates: List[str]) -> str:
        if i < 0 or i >= len(shots):
            return ""
        s = shots[i]
        for k in key_candidates:
            if k in s and s.get(k):
                return _safe_str(s.get(k))
        return ""

    hook = pick(0, ["台词", "台词要点", "画面内容", "画面"])
    middle = pick(1, ["画面内容", "画面", "台词", "台词要点"])
    highlight = pick(2, ["画面内容", "画面", "台词", "台词要点"])

    outline_sections = [
        "开头Hook：一句话抛结论/反转，引发好奇",
        "展开背景：场景/对象/痛点（为什么要看下去）",
        "核心内容：3个关键信息点（评价标准/步骤/对比）",
        "优点总结：1-2个让人想点赞/收藏的点",
        "槽点或注意：1-2个扣分点（语气可改犀利/客观）",
        "结尾CTA：建议+评论互动/关注收藏/点名下一期",
    ]

    story = [f"开头用一句话抛出结论：{one_liner or '先抛结论，再给反转/证据。'}"]
    if hook:
        story.append(f"Hook表现：{hook[:80]}{'…' if len(hook) > 80 else ''}")
    if middle:
        story.append(f"进入展开：{middle[:80]}{'…' if len(middle) > 80 else ''}")
    if highlight:
        story.append(f"关键评价点：{highlight[:80]}{'…' if len(highlight) > 80 else ''}")
    story.append("最后收束到建议与CTA：给出适合谁/值不值，并引导评论互动。")

    return {
        "主题": topic,
        "风格": style,
        "格式": fmt,
        "一句话梗概": one_liner,
        "目标受众": audience,
        "核心卖点": points[:5],
        "剧情梗概": "\n".join(story),
        "段落大纲": outline_sections,
        "镜头梗概": _shots_brief(shots, limit=8),
        "可修改点示例": [
            "开头hook更狠/更温和（先抛结论或先反转）",
            "第3镜头更严格/更犀利，并增加要点字幕",
            "信息点增加/减少，语气改更客观或更吐槽",
            "结尾CTA更强：评论投票/关注收藏/点名下一家",
        ],
        "说明": "这是梗概版（short outline）：用于确认走向并 revise。完整分镜大纲已保存，final 输出终稿脚本。传 detail: full 可返回完整 outline。",
    }


# -------------------------
# revise logic
# -------------------------
def _apply_notes_to_outline(outline: Dict[str, Any], notes: str) -> Dict[str, Any]:
    if not notes:
        return outline

    shots = _extract_shots(outline)

    mentions_third = ("第3" in notes) or ("第三" in notes) or ("3镜头" in notes)
    add_subtitle = ("字幕" in notes) or ("动作要点" in notes) or ("要点字幕" in notes)

    if mentions_third:
        i = _find_shot_index(shots, 3)
        if i != -1:
            s = shots[i]
            dialog_key = "台词" if "台词" in s else ("台词要点" if "台词要点" in s else "台词")
            dialog = _safe_str(s.get(dialog_key))
            strict_line = "【更严格提示】动作一定要慢、要稳；不标准就减次数，也不要硬撑。"
            if strict_line not in dialog:
                dialog = (dialog + "\n" + strict_line).strip() if dialog else strict_line
            s[dialog_key] = dialog

            if add_subtitle:
                sub_key = "字幕" if "字幕" in s else "字幕"
                subtitle = _safe_str(s.get(sub_key))
                add_line = "字幕要点：慢＝更有效｜核心收紧｜不要塌腰｜呼吸别憋"
                if add_line not in subtitle:
                    subtitle = (subtitle + "；" + add_line).strip("；") if subtitle else add_line
                s[sub_key] = subtitle

            shots[i] = s

    if ("hook" in notes.lower()) or ("更狠" in notes) or ("开头" in notes):
        key = "一句话梗概" if "一句话梗概" in outline else "一句话梗概"
        old = _safe_str(outline.get(key))
        if old:
            outline[key] = f"{old}（加强版：先抛结论，再给反转/证据，更抓人。）"
        else:
            outline[key] = "先抛结论再反转：更抓人的开头hook（加强版）。"

    _set_shots(outline, shots)
    outline["last_revision_note"] = notes
    outline["updated_at"] = _utc_now()
    return outline


# -------------------------
# final generation
# -------------------------
def _expand_full_script_from_outline(outline: Dict[str, Any], notes_merged: str = "") -> str:
    topic = _safe_str(outline.get("主题") or outline.get("topic") or "")
    style = _safe_str(outline.get("风格") or outline.get("style") or "")
    fmt = _safe_str(outline.get("格式") or outline.get("format") or "分镜")
    shots = _extract_shots(outline)

    lines: List[str] = []
    lines.append(f"【标题】{topic}".strip())
    if style:
        lines.append(f"【风格】{style}")
    lines.append(f"【输出格式】{fmt}")
    if notes_merged:
        lines.append(f"【确认/修改记录】{notes_merged}")
    lines.append("")
    lines.append("【完整版脚本（导演稿/口播稿）】")
    lines.append("")

    for idx, s in enumerate(shots, start=1):
        dur = _safe_str(s.get("时长") or s.get("duration") or "")
        visual = _safe_str(s.get("画面内容") or s.get("画面") or s.get("visual") or "")
        dialog = _safe_str(s.get("台词") or s.get("台词要点") or s.get("dialog") or "")
        subtitle = _safe_str(s.get("字幕") or s.get("subtitle") or "")
        sfx = _safe_str(s.get("音乐/音效") or s.get("音效") or s.get("bgm") or "")
        transition = _safe_str(s.get("转场") or s.get("transition") or "")

        lines.append(f"### 镜头 {idx}（{dur}）" if dur else f"### 镜头 {idx}")
        if visual:
            lines.append(f"- 画面：{visual}")
        if dialog:
            lines.append(f"- 口播：{dialog}")
        if subtitle:
            lines.append(f"- 字幕：{subtitle}")
        if sfx:
            lines.append(f"- 音乐/音效：{sfx}")
        if transition:
            lines.append(f"- 转场：{transition}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_final_script_page(outline: Dict[str, Any], notes_history: List[str]) -> str:
    topic = _safe_str(outline.get("主题") or outline.get("topic") or "")
    style = _safe_str(outline.get("风格") or outline.get("style") or "")
    fmt = _safe_str(outline.get("格式") or outline.get("format") or "分镜")
    one_liner = _safe_str(outline.get("一句话梗概") or outline.get("summary") or "")
    audience = _safe_str(outline.get("目标受众") or outline.get("受众") or outline.get("audience") or "")
    points = outline.get("核心卖点") or outline.get("卖点") or outline.get("points") or []
    if not isinstance(points, list):
        points = [str(points)] if points else []

    notes_merged = "；".join([n for n in notes_history if n])[:800]
    shots = _extract_shots(outline)

    hook = [
        "先抛结论：值不值？先给你一句话答案。",
        "再给证据：用3个点把你说服/劝退。",
        "最后给建议：适合谁、不适合谁，别踩坑。",
    ]
    if notes_merged:
        hook.append(f"（已按确认/修改点调整：{notes_merged}）")

    pages: List[str] = []
    pages.append("【终稿脚本（finalScriptPage）】")
    if topic:
        pages.append(f"标题：{topic}")
    if style:
        pages.append(f"风格：{style}")
    pages.append(f"输出方式：{fmt}")
    if one_liner:
        pages.append(f"一句话梗概：{one_liner}")
    if audience:
        pages.append(f"目标受众：{audience}")
    if points:
        pages.append("核心卖点：")
        for p in points[:6]:
            pages.append(f"- {p}")

    pages.append("")
    pages.append("========== Page 1：30秒 Hook（逐句口播） ==========")
    pages.extend(hook)

    pages.append("")
    pages.append("========== Page 2：主体（按镜头终稿化，可直接拍摄） ==========")
    for idx, s in enumerate(shots, start=1):
        dur = _safe_str(s.get("时长") or s.get("duration") or "")
        visual = _safe_str(s.get("画面内容") or s.get("画面") or s.get("visual") or "")
        dialog = _safe_str(s.get("台词") or s.get("台词要点") or s.get("dialog") or "")
        subtitle = _safe_str(s.get("字幕") or s.get("subtitle") or "")
        sfx = _safe_str(s.get("音乐/音效") or s.get("音效") or s.get("bgm") or "")

        header = f"【第{idx}镜】" + (f"（{dur}）" if dur else "")
        pages.append(header)
        if visual:
            pages.append(f"画面：{visual}")
        if sfx:
            pages.append(f"音乐/音效：{sfx}")

        pages.append("口播（终稿）：")
        if dialog:
            pages.append(f"- {dialog}")
        pages.append("- 结论先讲清楚，再给证据；别堆形容词，要给具体感受。")

        pages.append("字幕（终稿）：")
        if subtitle:
            pages.append(f"- {subtitle}")
        else:
            pages.append("- 结论｜证据｜建议（字幕三段式）")

        pages.append("剪辑提示：")
        pages.append("- 结论处上大字；证据处切特写；建议处加CTA。")
        pages.append("")

    pages.append("")
    pages.append("========== Page 3：CTA 收尾 ==========")
    pages.extend(
        [
            "你同意这个结论吗？评论区投票：值/不值。",
            "想看下一家测评？评论区点名，我下次就去。",
            "字幕收尾：关注＋收藏｜下次见",
        ]
    )

    return "\n".join([p for p in pages if p is not None]).strip()


# -------------------------
# entrypoint
# -------------------------
@app.entrypoint
def run(payload: Dict[str, Any], headers: Dict[str, Any]) -> str:
    try:
        prompt = payload.get("prompt", "")
        if not isinstance(prompt, str):
            prompt = json.dumps(prompt, ensure_ascii=False)

        kv = _parse_kv_lines(prompt)

        topic = (kv.get("topic") or kv.get("主题") or "").strip()
        style = (kv.get("style") or kv.get("风格") or "种草").strip()
        fmt = (kv.get("format") or kv.get("格式") or "分镜").strip()

        step = _normalize_step(kv.get("step") or kv.get("步骤") or "outline")
        detail = _normalize_detail(kv.get("detail") or kv.get("详细度") or "")
        draft_id = (kv.get("draft_id") or kv.get("草稿id") or kv.get("草稿ID") or kv.get("草稿") or "").strip()
        notes = (kv.get("notes") or kv.get("修改") or kv.get("反馈") or kv.get("确认") or "").strip()

        # ---------------- outline ----------------
        if step == "outline":
            if not topic:
                return json.dumps(
                    {
                        "错误": "缺少 topic。",
                        "示例": "topic: 巴黎拉面店探店测评\nstyle: 犀利吐槽+真实种草\nformat: 分镜\nstep: outline",
                        "说明": "outline/revise 默认返回梗概版；传 detail: full 可返回完整 outline；final 输出终稿脚本。",
                    },
                    ensure_ascii=False,
                )

            outline_obj = generate_script(topic=topic, style=style, fmt=fmt)
            outline_full = _to_plain_dict(outline_obj)

            new_id = uuid.uuid4().hex[:8]
            bundle = {
                "draft_id": new_id,
                "outline": outline_full,  # 存完整
                "notes_history": [],
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
            _save_draft_bundle(new_id, bundle)

            if detail == "full":
                out = dict(outline_full)
                out["说明"] = "这是完整 outline（full）。如需短梗概，去掉 detail: full。"
            else:
                out = _make_outline_summary(outline_full)

            out["draft_id"] = new_id
            out["step"] = "outline"
            out["next_step"] = "step: revise (可多次) / step: final"
            return json.dumps(out, ensure_ascii=False)

        # ---------------- revise ----------------
        if step == "revise":
            if not draft_id:
                return json.dumps(
                    {
                        "错误": "缺少 draft_id（请先 step:outline 获取）。",
                        "示例": "draft_id: ab12cd34\nstep: revise\nnotes: 第3镜头语气更严格，增加要点字幕",
                    },
                    ensure_ascii=False,
                )
            if not notes:
                return json.dumps(
                    {"错误": "缺少 notes（请输入要修改的点）。"},
                    ensure_ascii=False,
                )

            bundle = _load_draft_bundle(draft_id)
            if not bundle:
                return json.dumps(
                    {"错误": "draft_id 无效或已过期（文件不存在）。", "建议": "请重新 step:outline 生成新的 draft_id。"},
                    ensure_ascii=False,
                )

            outline_full = bundle.get("outline") or {}
            if not isinstance(outline_full, dict):
                outline_full = {}

            notes_history = bundle.get("notes_history") or []
            if not isinstance(notes_history, list):
                notes_history = []
            notes_history.append(notes)

            outline_full = _apply_notes_to_outline(outline_full, notes=notes)

            bundle["outline"] = outline_full
            bundle["notes_history"] = notes_history
            bundle["updated_at"] = _utc_now()
            _save_draft_bundle(draft_id, bundle)

            if detail == "full":
                out = dict(outline_full)
                out["说明"] = "这是完整 outline（full）。如需短梗概，去掉 detail: full。"
            else:
                out = _make_outline_summary(outline_full)

            out["draft_id"] = draft_id
            out["step"] = "revise"
            out["notes_history"] = notes_history[-10:]
            out["last_revision_note"] = notes
            out["next_step"] = "继续 step: revise 或 step: final"
            return json.dumps(out, ensure_ascii=False)

        # ---------------- final ----------------
        if step == "final":
            if not draft_id:
                return json.dumps(
                    {"错误": "缺少 draft_id（请先 step:outline 获取）。"},
                    ensure_ascii=False,
                )

            bundle = _load_draft_bundle(draft_id)
            if not bundle:
                return json.dumps(
                    {"错误": "draft_id 无效或已过期（文件不存在）。", "建议": "请重新 step:outline 生成新的 draft_id。"},
                    ensure_ascii=False,
                )

            outline_full = bundle.get("outline") or {}
            if not isinstance(outline_full, dict):
                outline_full = {}

            notes_history = bundle.get("notes_history") or []
            if not isinstance(notes_history, list):
                notes_history = []

            # final 时如果带 notes，当作最后一次修改再生成终稿
            if notes:
                notes_history.append(notes)
                outline_full = _apply_notes_to_outline(outline_full, notes=notes)
                bundle["outline"] = outline_full
                bundle["notes_history"] = notes_history
                bundle["updated_at"] = _utc_now()
                _save_draft_bundle(draft_id, bundle)

            notes_merged = "；".join([n for n in notes_history if n])

            full_script = _expand_full_script_from_outline(outline=outline_full, notes_merged=notes_merged)
            final_page = _build_final_script_page(outline=outline_full, notes_history=notes_history)

            out: Dict[str, Any] = dict(outline_full)
            out["draft_id"] = draft_id
            out["step"] = "final"
            out["notes_history"] = notes_history[-20:]
            out["full_script"] = full_script
            out["finalScriptPage"] = final_page
            return json.dumps(out, ensure_ascii=False)

        return json.dumps({"错误": f"未知 step: {step}", "允许值": ["outline", "revise", "final"]}, ensure_ascii=False)

    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Invocation failed: %s\n%s", e, tb)
        return json.dumps({"错误": str(e), "traceback": tb}, ensure_ascii=False)


@app.ping
def ping() -> str:
    return json.dumps({"status": "pong"}, ensure_ascii=False)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)