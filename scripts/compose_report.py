#!/usr/bin/env python3
"""Compose a bidding/tender big-data report by orchestrating the bidding MCP.

Calls the upstream bidding-mcp-server tools and assembles a structured JSON
payload rendered into a professional HTML / Markdown report. Supports
``--dry-run`` which returns a well-formed skeleton from the bundled sample data
WITHOUT contacting the MCP.

Workflow (real run, enterprise-centric):
  1. Resolve the canonical enterprise name (fuzzy search if only a keyword).
  2. Query bid_win_stats, tender_stats, procurement_stats, bidding_info, planned_projects.
  3. Build unified report JSON with domain sections (中标统计 / 招标统计 / 采购统计 / 拟建项目 / 招投标明细).
  4. Optionally render HTML + Markdown.

A market-search mode (`--search`) uses the keyword-based `bid_bigdata_bid_search`
to scan the public bidding market by type/region/amount/time, decoupled from any
specific enterprise. This file never prints secrets.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
from typing import Any, Dict, List, Mapping, Optional, Sequence

from common import REPORT_BANNER, REPORT_TYPE, attach_pagination, call_tool_once, collect_detail_pages, json_dumps, load_json_file, paid_call_scope, print_json
import mcp_client
from render_report import render_html, render_markdown, html_to_pdf

SAMPLE_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "report.example.json"

# Bidding MCP tools.
T_FUZZY = "bid_bigdata_fuzzy_search"
T_WIN_STATS = "bid_bigdata_bid_win_stats"
T_BIDDING_INFO = "bid_bigdata_bidding_info"
T_TENDER_STATS = "bid_bigdata_tender_stats"
T_PROCUREMENT_STATS = "bid_bigdata_procurement_stats"
T_BID_SEARCH = "bid_bigdata_bid_search"
T_PLANNED = "bid_bigdata_planned_projects"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _is_api_error(value: Any) -> bool:
    """Return True for failed MCP/tool envelopes, never for a successful empty result."""
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip().lower()
        return any(marker in text for marker in (
            "接口调用失败", "查询失败", "状态码：4", "状态码：5",
            "error executing tool", "validation error", "密钥错误", "鉴权失败",
        ))
    if isinstance(value, list):
        return any(_is_api_error(item) for item in value)
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("is_error") is True or value.get("success") is False:
            return True
        if value.get("_error") not in (None, "", False) or value.get("error") not in (None, "", False):
            return True
        if set(value) <= {"text", "code", "status", "message", "msg"} and value.get("text"):
            text = str(value.get("text")).strip()
            if "查询数据为空" in text:
                return False
            return True
        return any(
            _is_api_error(value.get(key))
            for key in ("text", "message", "msg", "detail", "content")
            if key in value
        )
    return False


def _first_list(value: Any) -> List[Any]:
    """Extract business records without turning envelopes into phantom rows."""
    if _is_api_error(value):
        return []
    if isinstance(value, list):
        cleaned: List[Any] = []
        for item in value:
            if _is_api_error(item) or item in (None, "", {}, []):
                continue
            if isinstance(item, dict):
                business_values = [v for k, v in item.items() if k not in {"total", "count", "code", "message", "msg"}]
                if business_values and all(v in (None, "", "-", [], {}) for v in business_values):
                    continue
            cleaned.append(item)
        return cleaned
    if isinstance(value, dict):
        for key in ("resultList", "storeList", "list", "items", "data", "records"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
        envelope_keys = {
            "text", "message", "msg", "code", "status", "success", "total", "count",
            "pageIndex", "pageSize", "isError", "is_error", "content", "structuredContent",
            "structured_content", "_error", "error",
        }
        if set(value) <= envelope_keys:
            return []
        if value:
            return [value]
    return []


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict) and not _is_api_error(record):
            return record
    return {}


def _text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        t = json.dumps(value, ensure_ascii=False)
    else:
        t = str(value)
    t = " ".join(t.split())
    if limit and len(t) > limit:
        return t[: limit - 1].rstrip() + "…"
    return t


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_call(tool: str, arguments: Dict[str, Any]) -> Any:
    try:
        result = call_tool_once(mcp_client.call_tool, tool, arguments)
        # Detect API error responses (405, etc.) and return error marker
        if _is_api_error(result):
            return {"_error": "API错误", "_raw": result}
        return result
    except Exception:
        return {"_error": "调用失败"}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


def _failed_tools(sources: Mapping[str, Any]) -> List[str]:
    """Return only safe tool/dimension labels for failed calls."""
    return [name for name, payload in sources.items() if _is_api_error(payload)]


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def resolve_enterprise_name(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {"keyword": "", "enterprise": "", "resolved": False, "reason": "关键词为空"}
    if any(suffix in raw for suffix in ("公司", "集团", "有限", "院", "厂", "中心", "事务所", "合作社", "合伙")):
        return {"keyword": raw, "enterprise": raw, "resolved": True, "reason": "视为企业全称"}
    fuzzy = _safe_call(T_FUZZY, {"matchKeyword": raw, "pageSize": 1})
    fuzzy_total = _int(_safe_total(fuzzy))
    if fuzzy_total is not None and fuzzy_total > 1:
        return {
            "keyword": raw,
            "enterprise": raw,
            "resolved": False,
            "reason": f"模糊查询返回多候选（{fuzzy_total}），未静默选择首条",
            "fuzzy_total": fuzzy_total,
        }
    record = _first_record(fuzzy)
    name = str(record.get("name") or "").strip()
    if name:
        return {"keyword": raw, "enterprise": name, "resolved": True, "reason": "由关键词模糊查询补全", "fuzzy_total": _int(_safe_total(fuzzy)), "record": record}
    return {"keyword": raw, "enterprise": raw, "resolved": False, "reason": "模糊查询未命中企业全称，按关键词直查"}


# --------------------------------------------------------------------------- #
# Distribution extraction helpers (bid stats return many nested list-of-dict)
# --------------------------------------------------------------------------- #

def _dist_rows(payload: Any, *keys: str, label_aliases: tuple = ("range", "subjectMatter", "area", "product"), count_aliases: tuple = ("count", "times")) -> List[Dict[str, Any]]:
    """Flatten the first nested list found under any of `keys` into {名称, 数量, 占比} rows."""
    payload = payload if isinstance(payload, dict) else {}
    target = None
    for key in keys:
        for item in _first_list(payload.get(key)):
            if isinstance(item, dict):
                target = payload.get(key)
                break
        if target is not None:
            break
    if target is None:
        return []
    rows = []
    for item in _first_list(target):
        if not isinstance(item, dict):
            continue
        label = "-"
        for alias in label_aliases:
            if item.get(alias) not in (None, "", []):
                label = _text(item.get(alias))
                break
        count = "-"
        for alias in count_aliases:
            if item.get(alias) not in (None, ""):
                count = _text(item.get(alias))
                break
        percent = _text(item.get("percent")) if item.get("percent") is not None else "-"
        rows.append({"名称": label, "数量": count, "占比": percent})
    return rows


def _trend_rows(payload: Any, key: str) -> List[Dict[str, Any]]:
    payload = payload if isinstance(payload, dict) else {}
    rows = []
    for item in _first_list(payload.get(key)):
        if not isinstance(item, dict):
            continue
        rows.append({"年份": _text(item.get("year")), "数量": _text(item.get("count"))})
    return rows


def _derive_core_metrics(metrics: List[Dict[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Derive additional metrics from core analysis sections."""
    win_area = core.get("win_area", []) if isinstance(core, dict) else []
    win_trend = core.get("win_trend", []) if isinstance(core, dict) else []
    role_dist = core.get("role_dist", []) if isinstance(core, dict) else []
    if isinstance(win_area, list) and win_area:
        metrics.append({"label": "中标地区项数", "value": str(len(win_area)), "hint": "上游返回的中标地区分布项数"})
        try:
            nums = [int(r.get("数量", 0) or 0) for r in win_area if str(r.get("数量", "0")).isdigit() or isinstance(r.get("数量"), (int, float))]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "地区CR3", "value": f"{top3/total*100:.1f}%", "hint": "返回地区项内前3合计；基准为返回项合计，不是全量地区"})
        except (ValueError, TypeError):
            pass
    if isinstance(win_trend, list) and win_trend:
        metrics.append({"label": "有中标记录年度数", "value": str(len(win_trend)), "hint": "上游趋势中出现的年度数，不等同于企业存续年限"})
    if isinstance(role_dist, list) and role_dist:
        metrics.append({"label": "展示记录角色类型数", "value": str(len(role_dist)), "hint": "仅统计本次展示的招投标明细记录"})
    return metrics


# --------------------------------------------------------------------------- #
# Enterprise profile helpers (from fuzzy_search record)
# --------------------------------------------------------------------------- #

def _extract_profile(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract enterprise profile fields from a fuzzy_search record."""
    return {
        "name": _text(record.get("name")),
        "reg_capital": record.get("regCapitalValue"),
        "reg_capital_coin": _text(record.get("regCapitalCoinType")),
        "annual_turnover": _text(record.get("annualTurnover")),
        "oper_status": _text(record.get("operStatus")),
        "enterprise_type": _text(record.get("enterpriseType")),
        "found_time": _text(record.get("foundTime")),
        "legal_rep": _text(record.get("legalRepresentative")),
        "address": _text(record.get("address")),
        "homepage": _text(record.get("homepage")),
    }


def _format_capital(val: Any, coin: str = "") -> str:
    """Format capital value: 10995210218.0 -> '109.95 亿'."""
    try:
        v = float(val)
        if v >= 1e8:
            s = f"{v / 1e8:.2f} 亿"
        elif v >= 1e4:
            s = f"{v / 1e4:.2f} 万"
        else:
            s = f"{v:.0f}"
        if coin:
            s += f" {coin}"
        return s
    except (TypeError, ValueError):
        return _text(val) if val else "-"


def _enrich_metrics_with_profile(metrics: List[Dict[str, Any]], record: Any) -> List[Dict[str, Any]]:
    """Append enterprise profile metrics from a fuzzy_search record."""
    if not isinstance(record, dict):
        return metrics
    _prof = _extract_profile(record)
    if _prof.get("reg_capital") and _prof["reg_capital"] not in ("-", "", None):
        metrics.append({"label": "注册资本", "value": _format_capital(_prof["reg_capital"], _prof.get("reg_capital_coin", "")), "hint": "工商登记注册资本"})
    if _prof.get("found_time") and _prof["found_time"] != "-":
        metrics.append({"label": "成立时间", "value": _prof["found_time"], "hint": "工商登记成立日期"})
    if _prof.get("oper_status") and _prof["oper_status"] != "-":
        metrics.append({"label": "经营状态", "value": _prof["oper_status"], "hint": "工商登记经营状态"})
    if _prof.get("enterprise_type") and _prof["enterprise_type"] != "-":
        metrics.append({"label": "企业类型", "value": _prof["enterprise_type"], "hint": "工商登记企业类型"})
    if _prof.get("legal_rep") and _prof["legal_rep"] != "-":
        metrics.append({"label": "法定代表人", "value": _prof["legal_rep"], "hint": "工商登记法定代表人"})
    return metrics


# --------------------------------------------------------------------------- #
# Subject / caliber / metrics
# --------------------------------------------------------------------------- #

def build_subject(raw: str, resolved: Mapping[str, Any], keyword_type: str) -> Dict[str, Any]:
    return {
        "enterprise": resolved.get("enterprise") or raw,
        "matchKeyword": resolved.get("enterprise") or raw,
        "keywordType": keyword_type,
        "match_raw": raw,
        "resolved": bool(resolved.get("resolved")),
        "resolve_reason": resolved.get("reason", ""),
    }


def build_caliber(subject: Mapping[str, Any]) -> Dict[str, Any]:
    products = [item["name"] for item in _requested_product_rows(subject, False)]
    return {
        "match_target": subject.get("enterprise") or subject.get("match_raw"),
        "match_type": f"标讯统计按企业主体匹配（keywordType={subject.get('keywordType', 'name')}）",
        "data_scope": "、".join(products),
        "products": products,
        "limit": "数据来自公开招投标与采购公示；少量项目可能存在录入延迟或信息不全。",
    }


def build_caliber_search(search_args: Mapping[str, Any]) -> Dict[str, Any]:
    filters: Mapping[str, Any] = search_args
    nested_filters = search_args.get("filters")
    if isinstance(nested_filters, dict):
        filters = nested_filters
    has_amount_filter = any(filters.get(key) not in (None, "") for key in ("biddingProjectMinAmount", "biddingProjectMaxAmount"))
    amount_limit = (" 已应用金额筛选；明细保留上游返回的项目金额与币种以供复核，但若上游未返回该字段则显示缺失，不能仅凭命中结果验证金额条件。"
                    if has_amount_filter else "")
    return {
        "match_target": search_args.get("matchKeyword") or "招投标市场（按关键词检索）",
        "match_type": "招投标市场检索（关键词 + 类型/地区/金额/时间）",
        "data_scope": "公开招投标公告（按检索条件命中）",
        "products": ["招投标检索"],
        "limit": "检索结果取决于关键词与过滤条件；统计范围以本次检索为准。" + amount_limit,
    }


def _requested_product_rows(subject: Mapping[str, Any], search_mode: bool) -> List[Dict[str, str]]:
    """Keep the source catalog identical to the tools requested by this mode."""
    if search_mode:
        return [{"name": "招投标检索", "product_id": "66bf124bf134a4c21b4fc34c"}]
    reason = str(subject.get("resolve_reason") or "")
    rows: List[Dict[str, str]] = []
    if reason and reason not in ("视为企业全称", "关键词为空"):
        rows.append({"name": "企业模糊查询", "product_id": "675cea1f0e009a9ea37edaa1"})
    if subject.get("blocked_reason"):
        return rows
    rows.extend([
        {"name": "中标信息统计", "product_id": "6707813f7427e966078e391d"},
        {"name": "招标信息统计", "product_id": "6707813f7427e966078e392f"},
        {"name": "采购信息统计", "product_id": "6725e5b9ba65854594baebbc"},
        {"name": "招投标信息", "product_id": "66bf124bf134a4c21b4fc2fa"},
        {"name": "拟建公告", "product_id": "66f3d8c064bd2be52d68a134"},
    ])
    return rows


def build_metrics(win: Mapping[str, Any], tender: Mapping[str, Any], proc: Mapping[str, Any], info_total: Any, planned_total: Any, core: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    core = core or {}
    sample_n = len(core.get("info_records") or [])
    metrics.append({"label": "招投标参与记录", "value": (_text(info_total) if info_total is not None else "-"), "hint": "上游招投标信息总量"})
    metrics.append({"label": "中标标的类型数", "value": _dist_count(win, "winbidStatList"), "hint": "上游返回的中标标的分布项数，不是中标项目数"})
    metrics.append({"label": "招标标的类型数", "value": _dist_count(tender, "tenderStatList"), "hint": "上游返回的招标标的分布项数，不是招标项目数"})
    metrics.append({"label": "采购产品类型数", "value": _dist_count(proc, "purchasingProductStatList"), "hint": "上游返回的采购产品分布项数"})
    # 金额只合计当前展示记录中 role=中标/候选且含金额的记录，避免把样本写成全量。
    win_amounts = core.get("win_amounts") or []
    if win_amounts:
        total_amt = sum(win_amounts)
        avg_amt = total_amt / len(win_amounts)
        scope = f"本次展示{sample_n}条中{len(win_amounts)}条含金额记录" if sample_n else f"{len(win_amounts)}条含金额记录"
        metrics.append({"label": "展示记录中标金额合计", "value": f"{total_amt:,.2f} 万元", "hint": f"{scope}；不是企业全量中标金额"})
        metrics.append({"label": "展示记录单笔均值", "value": f"{avg_amt:,.2f} 万元", "hint": f"{scope}的算术均值"})
    # 信息类型（仅统计当前展示记录）
    info_type_dist = core.get("info_type_dist") or []
    if info_type_dist:
        top_type = info_type_dist[0]
        metrics.append({"label": "展示记录主要类型", "value": f"{top_type.get('信息类型', '-')}（{top_type.get('数量', 0)}条）", "hint": f"仅统计本次展示{sample_n}条记录；括号内为该类型条数"})
    # 采购方数（与主要客户/采购方同一指标，只保留一个）
    customer_top = core.get("customer_top") or []
    if customer_top:
        metrics.append({"label": "展示记录采购方数", "value": str(len(customer_top)) + " 家", "hint": f"本次展示{sample_n}条记录中出现的采购方去重数"})
    metrics.append({"label": "拟建项目", "value": (_text(planned_total) if planned_total is not None else "-"), "hint": "上游拟建公告总量"})
    return [m for m in metrics if m.get("value") not in ("", None, "-")]


def _dist_count(payload: Any, key: str) -> str:
    payload = payload if isinstance(payload, dict) else {}
    lst = _first_list(payload.get(key))
    return str(len([x for x in lst if isinstance(x, dict)])) if lst else "-"


# --------------------------------------------------------------------------- #
# Core analysis (enterprise mode)
# --------------------------------------------------------------------------- #

def build_core_analysis(win: Any, tender: Any, proc: Any, info: Any, planned: Any) -> Dict[str, Any]:
    win = win if isinstance(win, dict) else {}
    tender = tender if isinstance(tender, dict) else {}
    proc = proc if isinstance(proc, dict) else {}

    win_amount = _dist_rows(win, "winbidAmountStatList", label_aliases=("range",))
    win_area = _dist_rows(win, "winbidAreaStat", label_aliases=("area",))
    win_subject = _dist_rows(win, "winbidStatList", label_aliases=("subjectMatter",))
    win_trend = _trend_rows(win, "winbidTrend")

    tender_amount = _dist_rows(tender, "tenderAmountStatList", label_aliases=("range",))
    tender_area = _dist_rows(tender, "tenderAreaStat", label_aliases=("area",))
    tender_subject = _dist_rows(tender, "tenderStatList", label_aliases=("subjectMatter",))
    tender_trend = _trend_rows(tender, "tenderTrend")

    proc_product = _dist_rows(proc, "purchasingProductStatList", label_aliases=("product",), count_aliases=("count",))
    proc_area = _dist_rows(proc, "purchasingAreaStatList", label_aliases=("area",), count_aliases=("times",))

    info_rows = []
    info_total = _safe_total(info)
    # Aggregations across bidding_info rows
    customer_counter: Dict[str, int] = {}
    role_counter: Dict[str, int] = {}
    info_type_counter: Dict[str, int] = {}
    win_amounts: List[float] = []
    for item in _first_list(info):
        if not isinstance(item, dict):
            continue
        info_rows.append({
            "公告标题": _text(item.get("title")) or "-",
            "公告类型": _text(item.get("infoType")) or "-",
            "招投标角色": _text(item.get("role")) or "-",
            "项目地区": _text(_flatten_region(item.get("projectRegion"))) or "-",
            "项目金额": _format_bid_amount(item.get("projectAmount")),
            "公告时间": _text(item.get("publishDate")) or "-",
            "标的物": _join_list(item.get("subjectMatterList")),
        })
        # 客户/采购方聚合 (purchasingBidderList: [{name, nameId}])
        for pb in _first_list(item.get("purchasingBidderList")):
            if isinstance(pb, dict):
                cname = _text(pb.get("name"))
                if cname:
                    customer_counter[cname] = customer_counter.get(cname, 0) + 1
        # 角色结构
        role = _text(item.get("role"))
        if role:
            role_counter[role] = role_counter.get(role, 0) + 1
        # 信息类型
        itype = _text(item.get("infoType"))
        if itype:
            info_type_counter[itype] = info_type_counter.get(itype, 0) + 1
        # 中标金额聚合（仅 role=中标/候选 的 projectAmount）
        if item.get("role") in ("中标", "候选"):
            amt = _float_amount(item.get("projectAmount"))
            if amt is not None:
                win_amounts.append(amt)

    customer_rows = [{"客户/采购方": k, "出现次数": v} for k, v in sorted(customer_counter.items(), key=lambda x: x[1], reverse=True)]
    role_rows = [{"角色": k, "数量": v} for k, v in sorted(role_counter.items(), key=lambda x: x[1], reverse=True)]
    info_type_rows = [{"信息类型": k, "数量": v} for k, v in sorted(info_type_counter.items(), key=lambda x: x[1], reverse=True)]

    planned_rows = []
    planned_total = _safe_total(planned)
    for item in _first_list(planned):
        if not isinstance(item, dict):
            continue
        planned_rows.append({
            "项目名称": _text(item.get("ppTitle")) or "-",
            "建设地点": _text(_flatten_region(item.get("ppRegion"))) or "-",
            "发布时间": _text(item.get("ppPublishTime")) or "-",
            "评审时间": _text(item.get("ppApprovalTime")) or "-",
            "待采设备": _join_list(item.get("deviceList")),
            "项目内容": _text(item.get("ppContent"), limit=120) or "-",
        })

    sections = [
        {"key": "win_subject", "title": "中标标的分布", "kind": "bar", "note": "按标的物统计中标数量与占比", "chart": {"name": "名称", "value": "数量", "orient": "h"}, "columns": [("标的物", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "win_amount", "title": "中标金额分布", "kind": "pie", "note": "按金额区间统计中标占比", "chart": {"name": "名称", "value": "数量", "donut": True}, "columns": [("金额区间", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "win_area", "title": "中标区域分布", "kind": "bar", "note": "按区域统计中标数量", "chart": {"name": "名称", "value": "数量", "orient": "v"}, "columns": [("区域", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "win_trend", "title": "中标趋势", "kind": "line", "note": "按年度统计中标数量", "chart": {"x": "年份", "y": "数量", "area": True}, "columns": [("年份", "年份"), ("数量", "数量")]},
        {"key": "tender_subject", "title": "招标标的分布", "kind": "bar", "note": "按标的物统计招标数量与占比", "chart": {"name": "名称", "value": "数量", "orient": "h"}, "columns": [("标的物", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "tender_amount", "title": "招标金额分布", "kind": "pie", "note": "按金额区间统计招标占比", "chart": {"name": "名称", "value": "数量", "donut": True}, "columns": [("金额区间", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "tender_area", "title": "招标区域分布", "kind": "bar", "note": "按区域统计招标数量", "chart": {"name": "名称", "value": "数量", "orient": "v"}, "columns": [("区域", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "tender_trend", "title": "招标趋势", "kind": "line", "note": "按年度统计招标数量", "chart": {"x": "年份", "y": "数量", "area": True}, "columns": [("年份", "年份"), ("数量", "数量")]},
        {"key": "proc_product", "title": "采购产品分布", "kind": "pie", "note": "按产品统计采购数量与占比", "chart": {"name": "名称", "value": "数量", "donut": True}, "columns": [("产品", "名称"), ("数量", "数量"), ("占比", "占比")]},
        {"key": "proc_area", "title": "采购区域分布", "kind": "bar", "note": "按地区统计采购客户数", "chart": {"name": "名称", "value": "数量", "orient": "v"}, "columns": [("地区", "名称"), ("客户数", "数量"), ("占比", "占比")]},
        {"key": "customer_top", "title": "主要客户/采购方", "kind": "bar", "note": "按招投标公告中出现的采购方/客户聚合（出现次数）", "chart": {"name": "客户/采购方", "value": "出现次数", "orient": "h"}, "columns": [("客户/采购方", "客户/采购方"), ("出现次数", "出现次数")]},
        {"key": "role_dist", "title": "角色结构", "kind": "pie", "note": "招标/中标/候选 角色占比", "chart": {"name": "角色", "value": "数量", "donut": True}, "columns": [("角色", "角色"), ("数量", "数量")]},
        {"key": "info_records", "title": "招投标参与明细", "kind": "table", "note": f"本次展示 {len(info_rows)} 条" + (f"；上游总量 {info_total}" if info_total is not None else "；上游未返回总量"),
         "columns": [("公告标题", "公告标题"), ("公告类型", "公告类型"), ("招投标角色", "招投标角色"), ("项目地区", "项目地区"), ("项目金额", "项目金额"), ("公告时间", "公告时间"), ("标的物", "标的物")]},
        {"key": "planned_records", "title": "拟建项目", "kind": "table", "note": f"本次展示拟建公告 {len(planned_rows)} 条" + (f"；上游总量 {planned_total}" if planned_total is not None else "；上游未返回总量"),
         "columns": [("项目名称", "项目名称"), ("建设地点", "建设地点"), ("发布时间", "发布时间"), ("评审时间", "评审时间"), ("待采设备", "待采设备"), ("项目内容", "项目内容")]},
    ]

    return {
        "sections": sections,
        "win_subject": win_subject,
        "win_amount": win_amount,
        "win_area": win_area,
        "win_trend": win_trend,
        "tender_subject": tender_subject,
        "tender_amount": tender_amount,
        "tender_area": tender_area,
        "tender_trend": tender_trend,
        "proc_product": proc_product,
        "proc_area": proc_area,
        "customer_top": customer_rows,
        "role_dist": role_rows,
        "info_type_dist": info_type_rows,
        "win_amounts": win_amounts,
        "info_records": info_rows,
        "planned_records": planned_rows,
    }


def _flatten_region(value: Any) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, (dict, list)):
            return _flatten_region(decoded)
    if isinstance(value, dict):
        fields = ("country", "province", "city", "district", "county", "address", "value")
        values = [value[k] for k in fields if k in value] or list(value.values())
        return " ".join(_flatten_region(v) for v in values if v not in (None, "", [], {}))
    if isinstance(value, list):
        return " ".join(_flatten_region(v) for v in value)
    return _text(value)


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(v) for v in value if v)
    return _text(value, limit=120)


def _float_amount(value: Any) -> Optional[float]:
    """projectAmount (单位: 万元) -> float, or None if missing/invalid."""
    if value in (None, "", []):
        return None
    if isinstance(value, dict):
        value = value.get("value") or value.get("amount")
    try:
        f = float(str(value).replace(",", "").replace("万", "").strip())
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return f


def _format_bid_amount(value: Any) -> str:
    amt = _float_amount(value)
    if amt is None:
        return "-"
    return f"{amt:,.2f} 万元"


# --------------------------------------------------------------------------- #
# Core analysis (market search mode)
# --------------------------------------------------------------------------- #

def build_core_analysis_search(search: Any) -> Dict[str, Any]:
    rows = []
    total = _safe_total(search)
    for item in _first_list(search):
        if not isinstance(item, dict):
            continue
        rows.append({
            "公告标题": _text(item.get("biddingAnncTitle")) or "-",
            "公告类型": _text(item.get("biddingInfoType")) or "-",
            "项目类型": _text(item.get("biddingProjectType")) or "-",
            "项目地区": _flatten_region(item.get("biddingRegion")) or "-",
            "公告时间": _text(item.get("biddingPublishTime")) or "-",
            "截止时间": _text(item.get("biddingEndTime")) or "-",
            "项目编号": _text(item.get("biddingProjectID")) or "-",
            "项目金额": _format_bid_amount(
                item.get("projectAmount")
                or item.get("biddingProjectAmount")
                or item.get("projectAmountValue")
            ),
            "币种": _text(
                item.get("projectAmountCurrency")
                or item.get("biddingProjectAmountCurrency")
                or item.get("currency")
            ) or "-",
        })
    sections = [
        {"key": "search_records", "title": "招投标检索明细", "kind": "table", "note": f"本次展示 {len(rows)} 条；上游总量为 {total}" if total is not None else f"本次展示 {len(rows)} 条；上游未返回总量",
         "columns": [("公告标题", "公告标题"), ("公告类型", "公告类型"), ("项目类型", "项目类型"), ("项目地区", "项目地区"), ("项目金额", "项目金额"), ("币种", "币种"), ("公告时间", "公告时间"), ("截止时间", "截止时间"), ("项目编号", "项目编号")]},
    ]
    return {"sections": sections, "search_records": rows}


# --------------------------------------------------------------------------- #
# Records / insights / abstract
# --------------------------------------------------------------------------- #

def build_records(core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for item in core.get("info_records") or core.get("search_records") or []:
        out.append({
            "标题": item.get("公告标题") or "-",
            "类型": item.get("公告类型") or "-",
            "角色/编号": item.get("招投标角色") or item.get("项目编号") or "-",
            "地区": item.get("项目地区") or "-",
            "时间": item.get("公告时间") or item.get("截止时间") or "-",
        })
    return out[:20]


def _share_value(row: Mapping[str, Any], share_key: str = "占比") -> Optional[float]:
    """Return an upstream share when it is a real number, else None.

    Upstream `percent` is a share of the full population, while `数量` may be a
    truncated top-N list. Treating them as the same denominator overstates CRn.
    """
    raw = row.get(share_key)
    if raw in (None, "", "-"):
        return None
    try:
        value = float(str(raw).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def _concentration(rows: List[Mapping[str, Any]], top_n: int = 3, name_key: str = "名称", value_key: str = "数量", share_key: str = "占比") -> Dict[str, Any]:
    """Compute top-N concentration from a returned distribution.

    When every row carries an upstream share, use those shares (basis =
    ``upstream_share``) so a truncated top-5 list is not mistaken for the whole
    population. Otherwise compute within the returned rows and say so via
    ``basis = returned_rows``.
    """
    items = []
    shares = []
    for r in rows:
        try:
            items.append((r.get(name_key, "-"), float(str(r.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            items.append((r.get(name_key, "-"), 0.0))
        shares.append(_share_value(r, share_key))
    total = sum(v for _, v in items)
    if not total:
        return {}
    items.sort(key=lambda x: x[1], reverse=True)
    if all(s is not None for s in shares):
        share_by_name = {r.get(name_key, "-"): s for r, s in zip(rows, shares) if s is not None}
        top_share = share_by_name.get(items[0][0], 0.0)
        cr = sum(s for s in sorted(shares, reverse=True)[:top_n])
        return {"top": items[0][0], "top_share": top_share, "cr": cr, "total": total,
                "n": len(items), "basis": "upstream_share"}
    cr = sum(v for _, v in items[:top_n]) / total * 100
    return {"top": items[0][0], "top_share": items[0][1] / total * 100, "cr": cr, "total": total,
            "n": len(items), "basis": "returned_rows"}


def _trend_analysis(rows: List[Mapping[str, Any]], as_of_year: Optional[int] = None) -> Dict[str, Any]:
    """Analyse a year series without comparing the wrong end of the list.

    Upstream returns years newest-first by default. This sorts by year, reports
    the peak (including ties), and computes year-over-year only from complete
    years: when `as_of_year` is present in the series it is reported as a
    partial year and excluded from the YoY comparison.
    """
    series = []
    for r in rows:
        year_raw = str(r.get("年份", "")).strip()
        try:
            year = int(year_raw[:4])
        except (TypeError, ValueError):
            continue
        try:
            value = float(str(r.get("数量", 0)).replace(",", ""))
        except (TypeError, ValueError):
            value = 0.0
        series.append((year, value))
    if not series:
        return {}
    series.sort(key=lambda x: x[0])
    years = [y for y, _ in series]
    nums = [v for _, v in series]
    peak = max(nums)
    peak_years = [str(y) for y, v in series if v == peak]
    latest_year = years[-1]
    partial_year = latest_year if as_of_year is not None and latest_year == as_of_year else None
    complete = [(y, v) for y, v in series if y != partial_year]
    yoy = ""
    direction = "持平"
    compare = ""
    if len(complete) >= 2:
        (prev_year, prev), (last_year, last) = complete[-2], complete[-1]
        compare = f"{last_year} 年较 {prev_year} 年"
        if prev > 0:
            pct = (last - prev) / prev * 100
            if pct > 5:
                direction = f"上升 {pct:.0f}%"
            elif pct < -5:
                direction = f"下降 {abs(pct):.0f}%"
            yoy = f"{compare}{direction}（{last:.0f} vs {prev:.0f}）"
    return {
        "peak_period": "、".join(peak_years),
        "peak_value": peak,
        "peak_years": peak_years,
        "direction": direction,
        "yoy": yoy,
        "compare": compare,
        "partial_year": partial_year,
        "partial_value": next((v for y, v in series if y == partial_year), None),
        "last": nums[-1],
        "years": len(series),
    }


def _conc_basis(conc: Mapping[str, Any]) -> str:
    if conc.get("basis") == "returned_rows":
        return f"（基准为返回的{conc.get('n', 0)}项合计，不是全量）"
    return ""


def _search_relevance_rows(rows: Sequence[Mapping[str, Any]], keyword: str) -> List[Dict[str, Any]]:
    """Tag search hits by whether the visible title contains the keyword."""
    token = "".join(str(keyword or "").casefold().split())
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        title = "".join(str(item.get("公告标题") or "").casefold().split())
        item["关键词相关性"] = "标题命中" if token and token in title else "标题未命中（需核对正文）"
        out.append(item)
    return out


def annotate_search_core(core: Mapping[str, Any], keyword: str) -> Dict[str, Any]:
    """Attach title-level keyword relevance to an existing search-mode core."""
    out = dict(core)
    rows = _search_relevance_rows(core.get("search_records") or [], keyword)
    out["search_records"] = rows
    sections = []
    for spec in core.get("sections") or []:
        if isinstance(spec, dict) and spec.get("key") == "search_records":
            hit_n = sum(1 for r in rows if r.get("关键词相关性") == "标题命中")
            spec = dict(spec)
            note = str(spec.get("note") or "")
            # Recompute the relevance clause instead of appending it again on
            # offline re-review of an already annotated payload.
            marker = "；标题直接含关键词"
            if marker in note:
                note = note.split(marker, 1)[0]
            spec["note"] = f"{note.strip('；')}；标题直接含关键词 {hit_n} 条，其余需核对正文".strip("；")
            columns = list(spec.get("columns") or [])
            if ("关键词相关性", "关键词相关性") not in columns:
                columns.append(("关键词相关性", "关键词相关性"))
            spec["columns"] = columns
        sections.append(spec)
    out["sections"] = sections
    return out


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], as_of_year: Optional[int] = None) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}
    info_n = metric_map.get("招投标参与记录")
    win_subj = core.get("win_subject") or []
    win_area = core.get("win_area") or []
    win_amount = core.get("win_amount") or []
    win_trend = core.get("win_trend") or []
    tender_subj = core.get("tender_subject") or []
    proc_prod = core.get("proc_product") or []
    search_rows = core.get("search_records") or []
    sample_n = len(core.get("info_records") or search_rows or [])

    if search_rows:
        keyword = str(subject.get("match_raw") or subject.get("matchKeyword") or "")
        hit_n = sum(1 for r in search_rows if r.get("关键词相关性") == "标题命中")
        titles: Dict[str, int] = {}
        for r in search_rows:
            t = str(r.get("公告标题") or "").strip()
            if t and t != "-":
                titles[t] = titles.get(t, 0) + 1
        repeated = sorted(((t, n) for t, n in titles.items() if n > 1), key=lambda x: x[1], reverse=True)
        if info_n:
            insights.append({
                "feature": "检索命中规模",
                "evidence": f"上游返回关键词“{keyword}”命中 {info_n} 条；本次展示 {sample_n} 条。",
                "interpretation": "命中数是关键词过滤后的公告条数，不是项目数、企业数或成交数；统计范围以本次检索条件为准。",
            })
        insights.append({
            "feature": "关键词相关性",
            "evidence": f"本次展示的 {sample_n} 条中，标题直接包含关键词 {hit_n} 条；其余 {sample_n - hit_n} 条仅在正文或其他字段命中，需逐条核对主题。",
            "interpretation": "标题未命中不等于无关，但也不能仅凭检索命中就认定属于目标主题；引用前应查看公告正文与标的物。",
        })
        if repeated:
            examples = "、".join(f"“{t}”×{n}" for t, n in repeated[:3])
            insights.append({
                "feature": "同题记录重复",
                "evidence": f"展示样本中有 {len(repeated)} 个标题重复出现，例如 {examples}。",
                "interpretation": "同题记录可能对应不同地区、批次或采购包；不能按标题去重后当作项目数，也不代表同一事件的更高置信度。",
            })
        return insights

    if info_n:
        insights.append({
            "feature": "招投标活跃度",
            "evidence": f"企业招投标参与记录 {info_n} 条（上游总量）。",
            "interpretation": "参与记录数量反映企业在招投标市场的收录活跃程度；角色字段来自上游，公告类型与角色不一致时需回看原文。",
        })
    if win_subj:
        conc = _concentration(win_subj, 3)
        if conc:
            if conc["basis"] == "upstream_share":
                evidence = f"“{conc['top']}”占全部标的提及约 {conc['top_share']:.1f}%；前 3 类合计 {conc['cr']:.1f}%（CR3，按上游占比合计）。"
            else:
                evidence = f"返回的 {conc['n']} 个标的项中，“{conc['top']}”占比约 {conc['top_share']:.0f}%，前 3 类合计 {conc['cr']:.0f}%（CR3，基准为返回项合计）。"
            insights.append({
                "feature": "中标标的集中度",
                "evidence": evidence,
                "interpretation": ("单一标的占比不足 10%，说明返回的标的分布较分散，不能据此认定企业只做某一类工程；"
                                   if conc["top_share"] < 10 else
                                   "标的集中度反映企业核心供应能力与主营业务领域；CR3 越高说明业务越聚焦。"),
            })
    if win_area:
        conc = _concentration(win_area, 3)
        if conc:
            insights.append({
                "feature": "中标区域集中度",
                "evidence": f"返回的 {conc['n']} 个地区中，“{conc['top']}”占比约 {conc['top_share']:.0f}%，前 3 区域合计 {conc['cr']:.0f}%（CR3）；基准为返回地区合计。",
                "interpretation": "该比例只描述上游返回地区的内部结构；上游未返回全部地区总量时，不能把它当作企业全国市场份额。",
            })
    if win_amount:
        conc = _concentration(win_amount, 2)
        if conc:
            insights.append({
                "feature": "中标金额区间",
                "evidence": f"“{conc['top']}”区间中标最多，占比约 {conc['top_share']:.0f}%{_conc_basis(conc)}。",
                "interpretation": "中标金额区间反映企业承接项目的规模量级；中大额占比高通常意味着具备承接大型项目的能力。",
            })
    if win_trend:
        ta = _trend_analysis(win_trend, as_of_year=as_of_year)
        if ta:
            peak_text = f"峰值出现在“{ta['peak_period']}”（{ta['peak_value']:.0f} 项）"
            if len(ta.get("peak_years") or []) > 1:
                peak_text = f"峰值年度为 {'、'.join(ta['peak_years'])}（各 {ta['peak_value']:.0f} 项）"
            parts = [peak_text]
            if ta.get("yoy"):
                parts.append(ta["yoy"])
            elif ta.get("partial_year"):
                parts.append("剔除不完整年度后可用年度不足，未计算同比")
            else:
                parts.append("可用年度不足，未计算同比")
            if ta.get("partial_year"):
                parts.append(f"{ta['partial_year']} 年为不完整年度（{ta.get('partial_value') or 0:.0f} 条，截至报告生成日），不纳入同比")
            insights.append({
                "feature": "中标趋势研判",
                "evidence": "；".join(parts) + "。",
                "interpretation": "年度序列来自上游统计口径；最新年度未满全年时下降不等于全年收缩，需结合完整年度和行业景气度判断。",
            })
    if tender_subj:
        conc = _concentration(tender_subj, 2)
        if conc:
            interp = ("招标标的分布分散，单一标的占比低；不能据此判断企业采购的主攻方向。" if conc["top_share"] < 10
                      else "招标标的反映企业对外采购的主要方向，可用于供应链分析与寻源参考。")
            insights.append({
                "feature": "招标需求方向",
                "evidence": f"“{conc['top']}”在招标标的中占比约 {conc['top_share']:.1f}%{_conc_basis(conc)}。",
                "interpretation": interp,
            })
    if proc_prod:
        conc = _concentration(proc_prod, 2)
        if conc:
            insights.append({
                "feature": "采购产品结构",
                "evidence": f"采购产品以“{conc['top']}”为主，占比约 {conc['top_share']:.0f}%{_conc_basis(conc)}。",
                "interpretation": "采购产品结构揭示企业的核心采购品类；该分布仅覆盖上游返回项。",
            })
    customer_top = core.get("customer_top") or []
    if customer_top:
        conc = _concentration(customer_top, 3, name_key="客户/采购方", value_key="出现次数", share_key="")
        total_cust = sum(int(r.get("出现次数", 0) or 0) for r in customer_top)
        if conc:
            insights.append({
                "feature": "主要客户/采购方集中度",
                "evidence": f"本次展示的 {sample_n} 条记录中出现 {len(customer_top)} 家采购方/客户，合计 {total_cust} 次提及；其中“{conc['top']}”提及最多（占展示提及约 {conc['top_share']:.0f}%），前 3 家合计 {conc['cr']:.0f}%。",
                "interpretation": "该比例仅描述展示记录中的提及结构，不是企业全量客户收入集中度；采购方名称去重未做主体归并，同名不同主体需核验。",
            })
    win_amounts = core.get("win_amounts") or []
    if win_amounts:
        total_amt = sum(win_amounts)
        avg_amt = total_amt / len(win_amounts)
        mx = max(win_amounts)
        insights.append({
            "feature": "中标金额规模",
            "evidence": f"本次展示的 {sample_n} 条记录中，{len(win_amounts)} 条中标/候选公告含金额；合计 {total_amt:,.2f} 万元，单笔均值 {avg_amt:,.2f} 万元，单笔最高 {mx:,.2f} 万元。",
            "interpretation": "金额只覆盖展示样本中明确返回 projectAmount 的记录；缺失金额不按 0 处理，也不能外推为企业全量中标金额。",
        })
    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "本次请求的维度未返回可计算分布的有效记录。",
            "interpretation": "这表示上游未返回相应数据或当前页为空，不等于企业没有招投标活动；不据此生成业务规模结论。",
        })
    return insights


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]]) -> str:
    name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
    parts = [f"本报告以“{name}”为分析对象，基于公开招投标与采购数据，系统呈现企业中标统计、招标统计、采购统计、拟建项目与招投标参与明细。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告同时给出中标/招标/采购的结构化分布与趋势解读，便于市场分析、合作伙伴评估与供应链决策参考。")
    return "".join(parts)


def build_abstract_search(search_args: Mapping[str, Any], core: Mapping[str, Any]) -> str:
    kw = search_args.get("matchKeyword") or "全部"
    rows = core.get("search_records") or []
    hit_n = sum(1 for r in rows if r.get("关键词相关性") == "标题命中")
    parts = [f"本报告以招投标市场检索为分析对象，关键词为“{kw}”，基于公开招投标公告，呈现按条件命中的招投标明细。"]
    if rows:
        parts.append(f"本次展示 {len(rows)} 条，其中标题直接含关键词 {hit_n} 条。")
    parts.append("命中数不等于项目数或成交数；标题未命中的记录需结合正文核对主题后再引用。")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Dry-run
# --------------------------------------------------------------------------- #

def build_dry_run_payload(raw: str, keyword_type: str, search: bool) -> Dict[str, Any]:
    try:
        sample = load_json_file(SAMPLE_PATH)
    except Exception:
        sample = {}
    sample = sample if isinstance(sample, dict) else {}
    subject = sample.get("subject") or {"enterprise": raw, "matchKeyword": raw, "keywordType": keyword_type, "match_raw": raw}
    subject = {**subject, "match_raw": raw, "keywordType": keyword_type}
    core = sample.get("core_analysis") or {}
    metrics = sample.get("metrics") or []
    return apply_content_review(_assemble(subject, core, metrics, dry_run=True, search_mode=search))


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _quality_report(core: Mapping[str, Any]) -> Dict[str, Any]:
    """Section-fill rate from final declared sections and their actual bodies.

    ``0`` is a populated body; None/''/[]/{} is empty. This is not an accuracy
    score and must not be described as one.
    """
    ca = core if isinstance(core, dict) else {}
    sections = ca.get("sections")
    if isinstance(sections, list):
        total = len(sections)
        populated = sum(1 for s in sections if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        keys = [k for k in ca if k not in ("sections", "source_status")]
        total = len(keys)
        populated = sum(1 for k in keys if ca.get(k) not in (None, "", [], {}))
    return {
        "total_sections": total,
        "populated_sections": populated,
        "empty_sections": total - populated,
        "coverage_pct": round(populated / max(1, total) * 100),
    }


def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: Sequence[Mapping[str, Any]], *, dry_run: bool, search_mode: bool = False, tool_errors: Optional[List[str]] = None) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics) if not search_mode else build_abstract_search(subject, core)
    records = build_records(core)
    insights = build_insights(subject, core, metrics, as_of_year=dt.datetime.now().year)
    quality_report = _quality_report(core)
    populated = quality_report["populated_sections"]
    if populated == 0:
        if subject.get("blocked_reason"):
            abstract = f"主体未唯一解析，已停止后续数据产品调用：{subject.get('blocked_reason')}。本报告不包含主体画像或业务结论。"
        elif tool_errors:
            abstract = "本次查询未获得有效核心数据，且存在上游调用失败维度：" + "、".join(tool_errors) + "。不据此生成业务规模或市场结论。"
        else:
            abstract = "本次查询未返回有效核心数据；报告仅记录查询边界，不生成业务规模或市场结论。"
        import sys
        print("⚠️ 质量门禁警告: 所有核心分析维度均无数据", file=sys.stderr)
    title = f"{subject.get('enterprise') or '招投标市场'} 标讯大数据报告"
    return {
        "report_type": REPORT_TYPE,
        "title": title,
        "banner": REPORT_BANNER,
        "subject": dict(subject),
        "abstract": abstract,
        "summary": abstract,
        "executive_summary": ((["主体解析受阻：" + str(subject.get("blocked_reason")) + "；已停止主体数据调用。"] if subject.get("blocked_reason") else (["数据缺口：" + "、".join(tool_errors or []) + "未成功返回，本报告仅呈现成功维度。"] if tool_errors else [])) + ([item["interpretation"] for item in insights][:5] or [abstract[:120]])),
        "metrics": list(metrics),
        "caliber": build_caliber(subject) if not search_mode else build_caliber_search(subject),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "bidding-mcp-server",
            "products": _requested_product_rows(subject, search_mode),
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "tool_errors": list(tool_errors or []),
            "blocked_reason": subject.get("blocked_reason"),
            "quality_report": quality_report,
            "search_mode": search_mode,
        },
    }


_REVIEW_METRIC_LABELS = {
    "中标标的数": "中标标的类型数",
    "招标标的数": "招标标的类型数",
    "采购产品数": "采购产品类型数",
    "总中标金额": "展示记录中标金额合计",
    "平均单笔金额": "展示记录单笔均值",
    "主要信息类型": "展示记录主要类型",
    "主要客户/采购方": "展示记录采购方数",
    "中标地区数": "中标地区项数",
    "中标年份跨度": "有中标记录年度数",
    "角色类型数": "展示记录角色类型数",
}
_DROP_METRIC_LABELS = {"采购方数"}


def _review_metrics(metrics: Sequence[Mapping[str, Any]], core: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Relabel sample-scoped metrics without adding or recomputing values."""
    sample_n = len(core.get("info_records") or core.get("search_records") or [])
    out: List[Dict[str, Any]] = []
    seen = set()
    for raw in metrics:
        if not isinstance(raw, dict):
            continue
        metric = dict(raw)
        label = str(metric.get("label") or "")
        if label in _DROP_METRIC_LABELS:
            continue
        label = _REVIEW_METRIC_LABELS.get(label, label)
        metric["label"] = label
        if label == "中标标的类型数":
            metric["hint"] = "上游返回的中标标的分布项数，不是中标项目数"
        elif label == "招标标的类型数":
            metric["hint"] = "上游返回的招标标的分布项数，不是招标项目数"
        elif label == "采购产品类型数":
            metric["hint"] = "上游返回的采购产品分布项数"
        elif label == "展示记录中标金额合计":
            metric["hint"] = f"本次展示{sample_n}条中含金额的中标/候选记录合计；不是企业全量中标金额"
        elif label == "展示记录单笔均值":
            metric["hint"] = f"本次展示{sample_n}条中含金额记录的算术均值"
        elif label == "展示记录主要类型":
            metric["hint"] = f"仅统计本次展示{sample_n}条记录；括号内为该类型条数"
        elif label == "展示记录采购方数":
            metric["hint"] = f"本次展示{sample_n}条记录中出现的采购方去重数"
        elif label == "中标地区项数":
            metric["hint"] = "上游返回的中标地区分布项数"
        elif label == "地区CR3":
            metric["hint"] = "返回地区项内前3合计；基准为返回项合计，不是全量地区"
        elif label == "有中标记录年度数":
            metric["hint"] = "上游趋势中出现的年度数，不等同于企业存续年限"
        elif label == "展示记录角色类型数":
            metric["hint"] = "仅统计本次展示的招投标明细记录"
        if label in seen:
            continue
        seen.add(label)
        out.append(metric)
    return out


def apply_content_review(report: Mapping[str, Any], *, source_sha256: Optional[str] = None,
                         reviewed_at: Optional[str] = None) -> Dict[str, Any]:
    """Rebuild bidding narrative content offline from an existing report payload.

    Uses only fields already present in the report (core distributions, metrics,
    subject, generated_at). It never calls the MCP and never adds facts. Fixes:
    * truncated top-N distributions interpreted as full-population CRn;
    * year trend compared at the wrong end of a newest-first series and
      treating the current partial year as a complete year;
    * sample-only amounts/types/customers presented as enterprise totals;
    * search hits without a title-level relevance marker.
    """
    out = copy.deepcopy(dict(report))
    core = out.get("core_analysis") or {}
    subject = out.get("subject") or {}
    ds = dict(out.get("data_source") or {})
    if subject.get("blocked_reason") or ds.get("blocked_reason"):
        ds["quality_report"] = _quality_report(core)
        ds["content_revision"] = {
            "mode": "offline_source_preserving",
            "source_sha256": source_sha256,
            "original_generated_at": ds.get("generated_at"),
            "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "主体未唯一解析/受阻报告：保留原阻断说明与空结果边界，不重算业务结论",
        }
        out["data_source"] = ds
        return out
    search_mode = bool(ds.get("search_mode")) or bool(core.get("search_records"))
    generated = str(ds.get("generated_at") or "")
    try:
        as_of_year = int(generated[:4]) if generated[:4].isdigit() else dt.datetime.now().year
    except (ValueError, TypeError):
        as_of_year = dt.datetime.now().year
    if search_mode:
        core = annotate_search_core(core, str(subject.get("match_raw") or subject.get("matchKeyword") or ""))
    metrics = _review_metrics(out.get("metrics") or [], core)
    quality = _quality_report(core)
    if quality["populated_sections"] == 0:
        # No business body: keep the assembled empty/failure narrative instead
        # of replacing it with a generic abstract that implies sections exist.
        out["core_analysis"] = core
        out["metrics"] = metrics
        ds["quality_report"] = quality
        ds["content_revision"] = {
            "mode": "offline_source_preserving",
            "source_sha256": source_sha256,
            "original_generated_at": ds.get("generated_at"),
            "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "scope": "无有效业务章节：保留原始空结果或调用失败说明，不生成业务结论",
        }
        out["data_source"] = ds
        return out
    insights = build_insights(subject, core, metrics, as_of_year=as_of_year)
    abstract = build_abstract_search(subject, core) if search_mode else build_abstract(subject, core, metrics)
    old_abstract = str(out.get("abstract") or "")
    marker = "明细含未完整采集的来源"
    if marker in old_abstract:
        # attach_pagination() appends this disclosure after the review; keep it
        # when an already-attached report is reviewed again offline.
        abstract += old_abstract[old_abstract.index(marker):]
    out["core_analysis"] = core
    out["metrics"] = metrics
    out["insights"] = insights
    out["abstract"] = abstract
    out["summary"] = abstract
    gap_lines = []
    if ds.get("tool_errors"):
        gap_lines = ["数据缺口：" + "、".join(str(item) for item in ds["tool_errors"]) + "未成功返回，本报告仅呈现成功维度。"]
    insight_lines = [item.get("interpretation") for item in insights][:5] or [abstract[:120]]
    out["executive_summary"] = gap_lines + insight_lines
    out["representative_records"] = build_records(core)
    ds["quality_report"] = _quality_report(core)
    ds["content_revision"] = {
        "mode": "offline_source_preserving",
        "source_sha256": source_sha256,
        "original_generated_at": ds.get("generated_at"),
        "reviewed_at": reviewed_at or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "重算口径文案与集中度基准；未新增查询、未改写原始记录字段",
    }
    out["data_source"] = ds
    return out


@paid_call_scope
def build_payload(raw: str, keyword_type: str, info_page_size: int, planned_page_size: int, max_pages: int = 1) -> Dict[str, Any]:
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages 必须为正整数")
    resolved = resolve_enterprise_name(raw)
    if not resolved.get("resolved"):
        subject = build_subject(raw, resolved, keyword_type)
        subject["blocked_reason"] = resolved.get("reason") or "企业主体未唯一解析"
        return apply_content_review(_assemble(subject, build_core_analysis({}, {}, {}, {}, {}), [], dry_run=False))
    enterprise = resolved["enterprise"]
    mk_args: Dict[str, Any] = {"matchKeyword": enterprise, "keywordType": keyword_type}
    win = _safe_call(T_WIN_STATS, mk_args)
    tender = _safe_call(T_TENDER_STATS, mk_args)
    proc = _safe_call(T_PROCUREMENT_STATS, mk_args)
    info = collect_detail_pages(_safe_call, T_BIDDING_INFO, {**mk_args, "pageSize": info_page_size},
                                get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
                                max_pages=max_pages)
    planned = collect_detail_pages(_safe_call, T_PLANNED, {**mk_args, "pageSize": planned_page_size},
                                   get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
                                   max_pages=max_pages)
    info_total = _safe_total(info) if isinstance(info, dict) else None
    planned_total = _safe_total(planned) if isinstance(planned, dict) else None

    subject = build_subject(raw, resolved, keyword_type)
    core = build_core_analysis(win, tender, proc, info, planned)
    metrics = build_metrics(win if isinstance(win, dict) else {}, tender if isinstance(tender, dict) else {}, proc if isinstance(proc, dict) else {}, info_total, planned_total, core)
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    # --- Enterprise profile enrichment (from fuzzy_search) ---
    _enrich_metrics_with_profile(metrics, resolved.get("record") if isinstance(resolved, dict) else None)
    # 失败维度只披露安全产品名称，不携带网关错误正文。
    tool_errors = _failed_tools({"中标信息统计": win, "招标信息统计": tender, "采购信息统计": proc, "招投标参与明细": info, "拟建项目": planned})
    report = apply_content_review(_assemble(subject, core, metrics, dry_run=False, tool_errors=tool_errors))
    return attach_pagination(report, {"招投标参与明细": info, "拟建项目": planned})


@paid_call_scope
def build_search_payload(args: argparse.Namespace) -> Dict[str, Any]:
    search_args: Dict[str, Any] = {"matchKeyword": args.search, "pageSize": args.page_size}
    for opt in ("bidding_type", "bidding_region", "pub_start", "pub_end", "search_mode", "purchasing_type", "min_amount", "max_amount"):
        val = getattr(args, opt, None)
        if val not in (None, ""):
            key = {
                "bidding_type": "biddingType", "bidding_region": "biddingRegion", "pub_start": "biddingAnncPubStartTime",
                "pub_end": "biddingAnncPubEndTime", "search_mode": "searchMode", "purchasing_type": "biddingPurchasingType",
                "min_amount": "biddingProjectMinAmount", "max_amount": "biddingProjectMaxAmount",
            }[opt]
            search_args[key] = val
    search = collect_detail_pages(_safe_call, T_BID_SEARCH, search_args,
                                  get_rows=_first_list, get_total=_safe_total, is_error=_is_api_error,
                                  max_pages=args.max_pages)
    core = annotate_search_core(build_core_analysis_search(search), args.search or "")
    subject = {"enterprise": args.search or "招投标市场", "matchKeyword": args.search, "keywordType": "market_search", "match_raw": args.search or "", "resolved": True, "resolve_reason": "市场检索模式", "filters": search_args}
    metrics: List[Dict[str, Any]] = []
    total = _safe_total(search)
    if total is not None:
        metrics.append({"label": "检索命中", "value": str(total), "hint": "本次检索命中招投标公告数"})
    report = apply_content_review(_assemble(subject, core, metrics, dry_run=False, search_mode=True, tool_errors=_failed_tools({"招投标检索": search})))
    return attach_pagination(report, {"招投标检索": search})


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Compose a bidding/tender big-data report via the bidding MCP.")
    parser.add_argument("--enterprise", help="企业全称或关键词（企业报告模式）")
    parser.add_argument("--keyword-type", default="name", help="主体类型：name/nameId/regNumber/socialCreditCode")
    parser.add_argument("--search", help="招投标市场检索关键词（市场检索模式；与 --enterprise 互斥）")
    parser.add_argument("--bidding-type", help="信息类型，list 字符串，如 '[\"招标公告\",\"中标公告\"]'")
    parser.add_argument("--bidding-region", help="项目地区，list of list 字符串，如 '[[\"福建省\",\"厦门市\"]]'")
    parser.add_argument("--pub-start", help="发布开始日期，如 2024-08-01")
    parser.add_argument("--pub-end", help="发布结束日期，如 2024-11-01")
    parser.add_argument("--search-mode", help="搜索模式：标题匹配/标的物匹配/全文匹配")
    parser.add_argument("--purchasing-type", help="招标单位类型，如 政府,学校")
    parser.add_argument("--min-amount", type=float, help="项目金额最小值（万）")
    parser.add_argument("--max-amount", type=float, help="项目金额最大值（万）")
    parser.add_argument("--page-size", type=int, default=20, help="明细分页大小（最多 50）；默认 20 以支撑客户/采购方聚合")
    parser.add_argument("--planned-page-size", type=int, default=10, help="拟建项目分页大小")
    parser.add_argument("--max-pages", type=int, default=1, help="规划的明细付费调用页数上限，默认1；先按 total 估算，只有必要且已授权时提高")
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    if not args.enterprise and not args.search:
        raise SystemExit("请提供 --enterprise（企业报告）或 --search（市场检索）")
    if args.enterprise and args.search:
        raise SystemExit("--enterprise 与 --search 互斥，请二选一")
    if args.max_pages is not None and args.max_pages < 1:
        raise SystemExit("--max-pages 必须为正整数")

    search_mode = bool(args.search) and not args.dry_run
    if args.dry_run:
        payload = build_dry_run_payload(args.enterprise or args.search or "", args.keyword_type, bool(args.search))
    elif args.search:
        payload = build_search_payload(args)
    else:
        payload = build_payload(args.enterprise, args.keyword_type, args.page_size, args.planned_page_size, args.max_pages)

    if args.output:
        out = pathlib.Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_dumps(payload, pretty=True), encoding="utf-8")
        print_json({"ok": True, "json": str(out), "dry_run": args.dry_run, "search_mode": search_mode})
    else:
        print_json(payload)

    if args.report_output:
        base_out = pathlib.Path(args.report_output).expanduser()
        base_out.parent.mkdir(parents=True, exist_ok=True)
        html_path = base_out.with_suffix(".html") if base_out.suffix.lower() not in (".html", ".htm") else base_out
        md_path = html_path.with_suffix(".md")
        html_path.write_text(render_html(payload), encoding="utf-8")
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        if args.pdf_output:
            pdf_path = pathlib.Path(args.pdf_output).expanduser()
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            html_to_pdf(render_html(payload), str(pdf_path))
        print_json({"ok": True, "html": str(html_path), "markdown": str(md_path), "pdf": str(pdf_path) if args.pdf_output else None, "dry_run": args.dry_run, "search_mode": search_mode})


if __name__ == "__main__":
    main()
