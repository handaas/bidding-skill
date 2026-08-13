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
import datetime as dt
import json
import pathlib
import sys
from typing import Any, Dict, List, Mapping, Optional

from common import REPORT_BANNER, REPORT_TYPE, json_dumps, load_json_file, print_json
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
    """Detect MCP API error responses (not empty data, but actual failures like 405)."""
    if value is None:
        return False
    if isinstance(value, str):
        return any(s in value for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5"))
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, str) and any(s in v for s in ("接口调用失败", "查询失败", "状态码：4", "状态码：5")):
                return True
    return False

def _first_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if _is_api_error(value):
            return []
        for key in ("resultList", "list", "items", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    if value in (None, "", {}):
        return []
    return [value]


def _first_record(value: Any) -> Dict[str, Any]:
    for record in _first_list(value):
        if isinstance(record, dict):
            return record
    if isinstance(value, dict):
        return value
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
        result = mcp_client.call_tool(tool, arguments)
        # Detect API error responses (405, etc.) and return error marker
        if _is_api_error(result):
            return {"_error": "API错误", "_raw": result}
        return result
    except Exception as exc:
        return {"_error": str(exc)}


def _safe_total(payload: Any) -> Any:
    if isinstance(payload, dict):
        if _is_api_error(payload):
            return None
        return payload.get("total")
    return None


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
    customer_top = core.get("customer_top", []) if isinstance(core, dict) else []
    role_dist = core.get("role_dist", []) if isinstance(core, dict) else []
    info_records = core.get("info_records", []) if isinstance(core, dict) else []
    if isinstance(win_area, list) and win_area:
        metrics.append({"label": "中标地区数", "value": str(len(win_area)), "hint": "中标项目覆盖的地区总数"})
        try:
            nums = [int(r.get("数量", 0) or 0) for r in win_area if str(r.get("数量", "0")).isdigit() or isinstance(r.get("数量"), (int, float))]
            total = sum(nums)
            if total > 0:
                top3 = sum(sorted(nums, reverse=True)[:3])
                metrics.append({"label": "地区CR3", "value": f"{top3/total*100:.1f}%", "hint": "前3大中标地区集中度"})
        except (ValueError, TypeError):
            pass
    if isinstance(win_trend, list) and win_trend:
        metrics.append({"label": "中标年份跨度", "value": str(len(win_trend)), "hint": "有中标记录的年度数"})
    if isinstance(customer_top, list) and customer_top:
        metrics.append({"label": "采购方数", "value": str(len(customer_top)), "hint": "不同采购方/客户数量"})
    if isinstance(role_dist, list) and role_dist:
        metrics.append({"label": "角色类型数", "value": str(len(role_dist)), "hint": "招投标中的角色类型数"})
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
    return {
        "match_target": subject.get("enterprise") or subject.get("match_raw"),
        "match_type": f"标讯统计按企业主体匹配（keywordType={subject.get('keywordType', 'name')}）",
        "data_scope": "中标统计、招标统计、采购统计、拟建项目、招投标参与明细",
        "products": ["中标信息统计", "招标信息统计", "采购信息统计", "招投标信息", "拟建公告"],
        "limit": "数据来自公开招投标与采购公示；少量项目可能存在录入延迟或信息不全。",
    }


def build_caliber_search(search_args: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "match_target": search_args.get("matchKeyword") or "招投标市场（按关键词检索）",
        "match_type": "招投标市场检索（关键词 + 类型/地区/金额/时间）",
        "data_scope": "公开招投标公告（按检索条件命中）",
        "products": ["招投标检索"],
        "limit": "检索结果取决于关键词与过滤条件；统计范围以本次检索为准。",
    }


def build_metrics(win: Mapping[str, Any], tender: Mapping[str, Any], proc: Mapping[str, Any], info_total: Any, planned_total: Any, core: Mapping[str, Any] = None) -> List[Dict[str, Any]]:
    metrics: List[Dict[str, Any]] = []
    core = core or {}
    info_n = _int(info_total) if info_total is not None else None
    planned_n = _int(planned_total) if planned_total is not None else None
    metrics.append({"label": "招投标参与记录", "value": (_text(info_total) if info_total is not None else "-"), "hint": "招投标信息条数"})
    metrics.append({"label": "中标标的数", "value": _dist_count(win, "winbidStatList"), "hint": "中标标的分布项数"})
    metrics.append({"label": "招标标的数", "value": _dist_count(tender, "tenderStatList"), "hint": "招标标的分布项数"})
    metrics.append({"label": "采购产品数", "value": _dist_count(proc, "purchasingProductStatList"), "hint": "采购产品分布项数"})
    # 总中标金额 / 平均单笔金额（万元）from aggregated 中标/候选 projectAmount
    win_amounts = core.get("win_amounts") or []
    if win_amounts:
        total_amt = sum(win_amounts)
        avg_amt = total_amt / len(win_amounts)
        metrics.append({"label": "总中标金额", "value": f"{total_amt:,.2f} 万", "hint": "已命中中标/候选公告金额合计"})
        metrics.append({"label": "平均单笔金额", "value": f"{avg_amt:,.2f} 万", "hint": "中标公告金额均值"})
    # 信息类型（出现次数最多的）
    info_type_dist = core.get("info_type_dist") or []
    if info_type_dist:
        top_type = info_type_dist[0]
        metrics.append({"label": "主要信息类型", "value": f"{top_type.get('信息类型', '-')}（{top_type.get('数量', 0)}）", "hint": "采购意向/中标公告等"})
    # 主要客户/采购方数
    customer_top = core.get("customer_top") or []
    if customer_top:
        metrics.append({"label": "主要客户/采购方", "value": str(len(customer_top)) + " 家", "hint": "公告中出现的采购方去重数"})
    metrics.append({"label": "拟建项目", "value": (_text(planned_total) if planned_total is not None else "-"), "hint": "拟建公告条数"})
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
        {"key": "info_records", "title": "招投标参与明细", "kind": "table", "note": f"本次命中 {info_total if info_total is not None else '若干'} 条，展示前若干条",
         "columns": [("公告标题", "公告标题"), ("公告类型", "公告类型"), ("招投标角色", "招投标角色"), ("项目地区", "项目地区"), ("项目金额", "项目金额"), ("公告时间", "公告时间"), ("标的物", "标的物")]},
        {"key": "planned_records", "title": "拟建项目", "kind": "table", "note": f"本次命中拟建公告 {planned_total if planned_total is not None else '若干'} 条，展示前 N 条",
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
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if v)
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
            "项目地区": _text(item.get("biddingRegion")) or "-",
            "公告时间": _text(item.get("biddingPublishTime")) or "-",
            "截止时间": _text(item.get("biddingEndTime")) or "-",
            "项目编号": _text(item.get("biddingProjectID")) or "-",
        })
    sections = [
        {"key": "search_records", "title": "招投标检索明细", "kind": "table", "note": f"本次检索命中 {total if total is not None else '若干'} 条，展示前 {len(rows)} 条",
         "columns": [("公告标题", "公告标题"), ("公告类型", "公告类型"), ("项目类型", "项目类型"), ("项目地区", "项目地区"), ("公告时间", "公告时间"), ("截止时间", "截止时间"), ("项目编号", "项目编号")]},
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


def _concentration(rows: List[Mapping[str, Any]], top_n: int = 3, name_key: str = "名称", value_key: str = "数量") -> Dict[str, Any]:
    """Compute top-N concentration (CRn) and dominant category from rows.

    Rows are dicts; `name_key` picks the label and `value_key` picks the numeric
    weight. Returns {} when there is no positive total.
    """
    items = []
    for r in rows:
        try:
            items.append((r.get(name_key, "-"), float(str(r.get(value_key, 0)).replace(",", ""))))
        except (TypeError, ValueError):
            items.append((r.get(name_key, "-"), 0.0))
    total = sum(v for _, v in items)
    if not total:
        return {}
    items.sort(key=lambda x: x[1], reverse=True)
    cr = sum(v for _, v in items[:top_n]) / total * 100
    return {"top": items[0][0], "top_share": items[0][1] / total * 100, "cr": cr, "total": total}


def _trend_analysis(rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
    """Compute trend direction, peak, and YoY change from {年份,数量} series."""
    nums = []
    for r in rows:
        try:
            nums.append(float(str(r.get("数量", 0)).replace(",", "")))
        except (TypeError, ValueError):
            nums.append(0.0)
    if not nums:
        return {}
    peak_idx = max(range(len(nums)), key=lambda i: nums[i])
    direction = "持平"
    yoy = ""
    if len(nums) >= 2:
        last, prev = nums[-1], nums[-2]
        if prev > 0:
            pct = (last - prev) / prev * 100
            if pct > 5:
                direction = f"上升 {pct:.0f}%"
            elif pct < -5:
                direction = f"下降 {abs(pct):.0f}%"
            yoy = f"同比 {pct:+.0f}%"
    return {"peak_period": rows[peak_idx].get("年份", "-"), "peak_value": nums[peak_idx], "direction": direction, "yoy": yoy, "last": nums[-1]}


def build_insights(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    insights: List[Dict[str, Any]] = []
    metric_map = {m["label"]: str(m["value"]) for m in metrics}
    info_n = metric_map.get("招投标参与记录")
    win_subj = core.get("win_subject") or []
    win_area = core.get("win_area") or []
    win_amount = core.get("win_amount") or []
    win_trend = core.get("win_trend") or []
    tender_subj = core.get("tender_subject") or []
    proc_prod = core.get("proc_product") or []

    if info_n:
        insights.append({
            "feature": "招投标活跃度",
            "evidence": f"企业招投标参与记录 {info_n} 条。",
            "interpretation": "参与记录数量反映企业在招投标市场的活跃程度；结合角色（招标/中标）可判断其采购与供应角色。",
        })
    if win_subj:
        conc = _concentration(win_subj, 3)
        if conc:
            insights.append({
                "feature": "中标标的集中度",
                "evidence": f"“{conc['top']}”占比约 {conc['top_share']:.0f}%，前 3 类合计 {conc['cr']:.0f}%（CR3）。",
                "interpretation": "中标标的集中度反映企业核心供应能力与主营业务领域；CR3 越高说明业务越聚焦，反之则供应能力更综合。",
            })
    if win_area:
        conc = _concentration(win_area, 3)
        if conc:
            insights.append({
                "feature": "中标区域集中度",
                "evidence": f"中标区域以“{conc['top']}”为主，占比约 {conc['top_share']:.0f}%，前 3 区域合计 {conc['cr']:.0f}%。",
                "interpretation": "中标区域集中度反映企业市场覆盖；集中度高代表深耕优势区域，分散则说明全国化布局，但单一区域依赖也存在市场收缩风险。",
            })
    if win_amount:
        conc = _concentration(win_amount, 2)
        if conc:
            insights.append({
                "feature": "中标金额区间",
                "evidence": f"“{conc['top']}”区间中标最多，占比约 {conc['top_share']:.0f}%。",
                "interpretation": "中标金额区间反映企业承接项目的规模量级；中大额占比高通常意味着具备承接大型项目的能力。",
            })
    if win_trend:
        ta = _trend_analysis(win_trend)
        if ta:
            insights.append({
                "feature": "中标趋势研判",
                "evidence": f"峰值出现在“{ta['peak_period']}”（{ta['peak_value']:.0f} 项），近年趋势{ta['direction']}，{ta.get('yoy', '')}。",
                "interpretation": "中标量上升通常意味着市场拓展能力增强、客户认可度提升；下降则可能源于竞争加剧或项目周期性收缩，需结合行业景气度判断。",
            })
    if tender_subj:
        conc = _concentration(tender_subj, 2)
        if conc:
            insights.append({
                "feature": "招标需求方向",
                "evidence": f"招标标的以“{conc['top']}”为主，占比约 {conc['top_share']:.0f}%。",
                "interpretation": "招标标的反映企业对外采购的主要方向，可用于供应链分析与寻源参考。",
            })
    if proc_prod:
        conc = _concentration(proc_prod, 2)
        if conc:
            insights.append({
                "feature": "采购产品结构",
                "evidence": f"采购产品以“{conc['top']}”为主，占比约 {conc['top_share']:.0f}%。",
                "interpretation": "采购产品结构揭示企业的核心采购品类，结合区域分布可评估供应链布局。",
            })
    # 主要客户/采购方集中度（CR3）— HIGHEST VALUE
    customer_top = core.get("customer_top") or []
    if customer_top:
        conc = _concentration(customer_top, 3, name_key="客户/采购方", value_key="出现次数")
        total_cust = sum(int(r.get("出现次数", 0) or 0) for r in customer_top)
        if conc:
            insights.append({
                "feature": "主要客户/采购方集中度",
                "evidence": f"公告中共出现 {len(customer_top)} 家采购方/客户，合计 {total_cust} 次提及；其中“{conc['top']}”提及最多（占比约 {conc['top_share']:.0f}%），前 3 家合计 {conc['cr']:.0f}%（CR3）。",
                "interpretation": "客户集中度反映企业收入来源的稳定性：集中度高说明核心大客户依赖强、关系稳定，但也存在大客户流失风险；分散则客户基础更广、抗周期能力更强。",
            })
    # 中标金额规模洞察
    win_amounts = core.get("win_amounts") or []
    if win_amounts:
        total_amt = sum(win_amounts)
        avg_amt = total_amt / len(win_amounts)
        mx = max(win_amounts)
        insights.append({
            "feature": "中标金额规模",
            "evidence": f"已命中 {len(win_amounts)} 条中标/候选公告，金额合计 {total_amt:,.2f} 万元，单笔均值 {avg_amt:,.2f} 万元，单笔最高 {mx:,.2f} 万元。",
            "interpretation": "中标金额规模反映企业承接项目的体量与议价能力；中大额项目占比高通常意味着具备承接大型订单的能力与品牌背书。",
        })
    if not insights:
        insights.append({
            "feature": "数据完整性",
            "evidence": "部分维度未返回有效数据。",
            "interpretation": "建议核对匹配关键词是否为企业全称，或检查 MCP 连接与上游数据产品覆盖范围。",
        })
    return insights


def build_abstract(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]]) -> str:
    name = subject.get("enterprise") or subject.get("match_raw") or "目标企业"
    parts = [f"本报告以“{name}”为分析对象，基于公开招投标与采购数据，系统呈现企业中标统计、招标统计、采购统计、拟建项目与招投标参与明细。"]
    if metrics:
        kv = "、".join(f"{m['label']} {m['value']}" for m in metrics[:5])
        parts.append(f"关键指标包括：{kv}。")
    parts.append("报告同时给出中标/招标/采购的结构化分布与趋势解读，便于市场分析、合作伙伴评估与供应链决策参考。")
    return "".join(parts)


def build_abstract_search(search_args: Mapping[str, Any], core: Mapping[str, Any]) -> str:
    kw = search_args.get("matchKeyword") or "全部"
    parts = [f"本报告以招投标市场检索为分析对象，关键词为“{kw}”，基于公开招投标公告，呈现按条件命中的招投标明细。"]
    parts.append("可用于政府采购人员查找合适的招标项目、企业查找投标机会以及分析招投标市场趋势。")
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
    return _assemble(subject, core, metrics, dry_run=True, search_mode=search)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def _assemble(subject: Mapping[str, Any], core: Mapping[str, Any], metrics: List[Mapping[str, Any]], *, dry_run: bool, search_mode: bool = False) -> Dict[str, Any]:
    abstract = build_abstract(subject, core, metrics) if not search_mode else build_abstract_search(subject, core)
    records = build_records(core)
    insights = build_insights(subject, core, metrics)
    # Quality gate: count populated core-analysis sections.
    ca = core if isinstance(core, dict) else {}
    secs = ca.get("sections", [])
    if secs:
        total_secs = len(secs)
        populated = sum(1 for s in secs if isinstance(s, dict) and ca.get(s.get("key")) not in (None, "", [], {}))
    else:
        total_secs = max(1, len([k for k in ca if k != "sections"]))
        populated = sum(1 for k in ca if k != "sections" and ca.get(k) not in (None, "", [], {}))
    quality_report = {
        "total_sections": total_secs,
        "populated_sections": populated,
        "empty_sections": total_secs - populated,
        "coverage_pct": round(populated / max(1, total_secs) * 100),
    }
    if populated == 0:
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
        "executive_summary": [item["interpretation"] for item in insights][:5] or [abstract[:120]],
        "metrics": list(metrics),
        "caliber": build_caliber(subject) if not search_mode else build_caliber_search(subject),
        "core_analysis": dict(core),
        "representative_records": records,
        "insights": insights,
        "data_source": {
            "mcp_server": "bidding-mcp-server",
            "products": [
                {"name": "中标信息统计", "product_id": "6707813f7427e966078e391d"},
                {"name": "招投标信息", "product_id": "66bf124bf134a4c21b4fc2fa"},
                {"name": "招标信息统计", "product_id": "6707813f7427e966078e392f"},
                {"name": "采购信息统计", "product_id": "6725e5b9ba65854594baebbc"},
                {"name": "招投标检索", "product_id": "66bf124bf134a4c21b4fc34c"},
                {"name": "拟建公告", "product_id": "66f3d8c064bd2be52d68a134"},
            ],
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "dry_run": dry_run,
            "quality_report": quality_report,
            "search_mode": search_mode,
        },
    }


def build_payload(raw: str, keyword_type: str, info_page_size: int, planned_page_size: int) -> Dict[str, Any]:
    resolved = resolve_enterprise_name(raw)
    enterprise = resolved["enterprise"]
    mk_args: Dict[str, Any] = {"matchKeyword": enterprise, "keywordType": keyword_type}
    win = _safe_call(T_WIN_STATS, mk_args)
    tender = _safe_call(T_TENDER_STATS, mk_args)
    proc = _safe_call(T_PROCUREMENT_STATS, mk_args)
    info = _safe_call(T_BIDDING_INFO, {**mk_args, "pageSize": info_page_size})
    planned = _safe_call(T_PLANNED, {**mk_args, "pageSize": planned_page_size})
    info_total = _safe_total(info) if isinstance(info, dict) else None
    planned_total = _safe_total(planned) if isinstance(planned, dict) else None

    subject = build_subject(raw, resolved, keyword_type)
    core = build_core_analysis(win, tender, proc, info, planned)
    metrics = build_metrics(win if isinstance(win, dict) else {}, tender if isinstance(tender, dict) else {}, proc if isinstance(proc, dict) else {}, info_total, planned_total, core)
    _derive_core_metrics(metrics, core if isinstance(core, dict) else {})
    # --- Enterprise profile enrichment (from fuzzy_search) ---
    _enrich_metrics_with_profile(metrics, resolved.get("record") if isinstance(resolved, dict) else None)
    return _assemble(subject, core, metrics, dry_run=False)


def build_search_payload(args: argparse.Namespace) -> Dict[str, Any]:
    search_args: Dict[str, Any] = {"matchKeyword": args.search, "pageIndex": 1, "pageSize": args.page_size}
    for opt in ("bidding_type", "bidding_region", "pub_start", "pub_end", "search_mode", "purchasing_type", "min_amount", "max_amount"):
        val = getattr(args, opt, None)
        if val not in (None, ""):
            key = {
                "bidding_type": "biddingType", "bidding_region": "biddingRegion", "pub_start": "biddingAnncPubStartTime",
                "pub_end": "biddingAnncPubEndTime", "search_mode": "searchMode", "purchasing_type": "biddingPurchasingType",
                "min_amount": "biddingProjectMinAmount", "max_amount": "biddingProjectMaxAmount",
            }[opt]
            search_args[key] = val
    search = _safe_call(T_BID_SEARCH, search_args)
    core = build_core_analysis_search(search)
    subject = {"enterprise": args.search or "招投标市场", "matchKeyword": args.search, "keywordType": "market_search", "match_raw": args.search or "", "resolved": True, "resolve_reason": "市场检索模式"}
    metrics: List[Dict[str, Any]] = []
    total = _safe_total(search)
    if total is not None:
        metrics.append({"label": "检索命中", "value": str(total), "hint": "本次检索命中招投标公告数"})
    return _assemble(subject, core, metrics, dry_run=False, search_mode=True)


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
    parser.add_argument("--dry-run", action="store_true", help="不调用真实 MCP，使用样例数据组装报告骨架")
    parser.add_argument("--output", help="输出 JSON 路径；省略则打印到 stdout")
    parser.add_argument("--report-output", help="同时输出 HTML 报告（.html）与 Markdown 报告（.md）")
    parser.add_argument("--pdf-output", help="额外输出 PDF 报告（.pdf）；需要 Playwright + Chromium")
    args = parser.parse_args()

    if not args.enterprise and not args.search:
        raise SystemExit("请提供 --enterprise（企业报告）或 --search（市场检索）")
    if args.enterprise and args.search:
        raise SystemExit("--enterprise 与 --search 互斥，请二选一")

    search_mode = bool(args.search) and not args.dry_run
    if args.dry_run:
        payload = build_dry_run_payload(args.enterprise or args.search or "", args.keyword_type, bool(args.search))
    elif args.search:
        payload = build_search_payload(args)
    else:
        payload = build_payload(args.enterprise, args.keyword_type, args.page_size, args.planned_page_size)

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
