#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch recent policy metadata from official MEE pages and write:
  data/live-policies.js
  data/live-meta.json
This script stores metadata/short summaries, not full policy text.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_JS = ROOT / "data" / "live-policies.js"
OUT_META = ROOT / "data" / "live-meta.json"

TZ_CN = timezone(timedelta(hours=8))

SOURCES = [
    ("生态环境部-部文件", "https://www.mee.gov.cn/zcwj/bwj/wj/"),
    ("生态环境部-公告", "https://www.mee.gov.cn/zcwj/bwj/gg/"),
    ("生态环境部-办公厅文件", "https://www.mee.gov.cn/zcwj/bgtwj/wj/"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PolicyMarketDatabase/1.0; +https://github.com/)"
}

session = requests.Session()
session.headers.update(HEADERS)

DATE_RE = re.compile(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})")
DOC_RE = re.compile(r"((?:环|发改|国办|国发|公告)[^\s，。；]{0,16}[〔\[]20\d{2}[〕\]][^\s，。；]{0,12}号)")
CARBON_WORDS = ("碳排放", "碳市场", "碳达峰", "碳中和", "气候变化", "温室气体", "自愿减排", "CCER", "配额", "履约")
CCER_WORDS = ("CCER", "自愿减排", "方法学")
GREEN_WORDS = ("绿证", "绿色电力")
MARKET_WORDS = ("全国碳排放权交易市场", "全国碳市场", "重点排放单位", "配额清缴")

def norm_date(text: str) -> str:
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def category_for(text: str) -> str:
    upper = text.upper()
    if any(w.upper() in upper for w in CCER_WORDS):
        return "CCER政策"
    if any(w in text for w in GREEN_WORDS):
        return "绿电绿证"
    if any(w in text for w in MARKET_WORDS):
        return "全国碳市场"
    if any(w in text for w in CARBON_WORDS):
        return "生态环境综合政策"
    return "生态环境综合政策"

def market_for(text: str) -> str:
    upper = text.upper()
    if any(w.upper() in upper for w in CCER_WORDS):
        return "CCER"
    if any(w in text for w in GREEN_WORDS):
        return "绿证"
    if any(w in text for w in MARKET_WORDS):
        return "全国CEA"
    if "气候变化" in text or "碳达峰" in text or "碳中和" in text:
        return "气候政策"
    return "其他"

def page_urls(base: str, pages: int = 5):
    yield base
    for i in range(1, pages):
        yield urljoin(base, f"index_{i}.shtml")

def fetch(url: str) -> str:
    r = session.get(url, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def extract_listing(source_name: str, base: str):
    found = {}
    for page_url in page_urls(base):
        try:
            html = fetch(page_url)
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text(" ", strip=True))
            href = urljoin(page_url, a["href"])
            if not title or len(title) < 6:
                continue
            if not href.startswith("http"):
                continue
            parent_text = clean_text(a.parent.get_text(" ", strip=True) if a.parent else "")
            date = norm_date(parent_text)
            if not date:
                continue
            if "mee.gov.cn" not in href:
                continue
            found[href] = {"source_name": source_name, "date": date, "title": title, "source_url": href}
        time.sleep(0.25)
    return list(found.values())

def parse_detail(item: dict) -> dict:
    try:
        html = fetch(item["source_url"])
    except Exception:
        html = ""
    soup = BeautifulSoup(html, "html.parser") if html else None
    full_text = clean_text(soup.get_text("\n", strip=True)) if soup else item["title"]

    title = item["title"]
    if soup:
        meta_title = soup.find("meta", attrs={"name":"ArticleTitle"})
        if meta_title and meta_title.get("content"):
            title = clean_text(meta_title["content"])

    date = item["date"]
    if soup:
        meta_date = soup.find("meta", attrs={"name":"PubDate"})
        if meta_date and meta_date.get("content"):
            date = norm_date(meta_date["content"]) or date

    doc = ""
    dm = DOC_RE.search(full_text)
    if dm:
        doc = clean_text(dm.group(1))

    publisher = "生态环境部"
    pm = re.search(r"发布机关\s*(.*?)\s*(?:生成日期|文\s*号|文　　号|主题词|主 题 词)", full_text)
    if pm:
        p = clean_text(pm.group(1))
        if 1 < len(p) < 120:
            publisher = p

    # Short factual summary: prefer meta description, otherwise first relevant sentence.
    summary = ""
    if soup:
        desc = soup.find("meta", attrs={"name":"description"})
        if desc and desc.get("content"):
            d = clean_text(desc["content"])
            if d and "中华人民共和国生态环境部" not in d:
                summary = d[:180]
    if not summary:
        # Avoid nav/footer by taking text around title where possible
        pos = full_text.find(title)
        segment = full_text[pos:pos+900] if pos >= 0 else full_text[:900]
        sentences = [clean_text(x) for x in re.split(r"[。！？]", segment) if len(clean_text(x)) >= 18]
        summary = (sentences[1] if len(sentences) > 1 else (sentences[0] if sentences else title))[:180]

    combined = f"{title} {summary} {full_text[:2500]}"
    category = category_for(combined)
    market = market_for(combined)
    status = "征求意见" if ("征求意见" in title or "征求意见" in combined[:800]) else "有效"

    scope = ["全国"]
    industries = []
    for kw in ("发电","钢铁","水泥","铝冶炼","石化","化工","建筑","交通","农业","林业","能源","电力"):
        if kw in combined and kw not in industries:
            industries.append(kw)
    if not industries:
        industries = ["生态环境"]

    return {
        "id": abs(hash(item["source_url"])) % 900000000 + 100000000,
        "date": date,
        "title": title,
        "doc": doc,
        "publisher": publisher,
        "category": category,
        "status": status,
        "market": market,
        "summary": summary or title,
        "source_url": item["source_url"],
        "scope": scope,
        "industries": industries,
        "parameters": [["结构化状态","待进一步提取"]],
        "compliance": [["执行节点","待进一步提取"]],
        "impact": "市场影响需结合真实交易数据计算，不由采集程序主观判断。"
    }

def main():
    items = []
    seen = set()
    for source_name, base in SOURCES:
        for x in extract_listing(source_name, base):
            if x["source_url"] not in seen:
                seen.add(x["source_url"])
                items.append(x)

    # Newest first, limit detail requests for robustness.
    items.sort(key=lambda x: x["date"], reverse=True)
    items = items[:80]

    policies = []
    for i, item in enumerate(items, 1):
        try:
            policies.append(parse_detail(item))
        except Exception as e:
            print("detail failed:", item["source_url"], e)
        if i % 10 == 0:
            time.sleep(0.5)

    policies.sort(key=lambda x: x["date"], reverse=True)
    generated = datetime.now(TZ_CN).isoformat(timespec="seconds")
    meta = {
        "generated_at": generated,
        "source_label": "MEE实时",
        "source_count": len(SOURCES),
        "policy_count": len(policies),
        "mode": "live"
    }

    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    js = "window.LIVE_POLICY_META = " + json.dumps(meta, ensure_ascii=False, indent=2) + ";\n"
    js += "window.LIVE_POLICIES = " + json.dumps(policies, ensure_ascii=False, indent=2) + ";\n"
    OUT_JS.write_text(js, encoding="utf-8")
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(policies)} policies")

if __name__ == "__main__":
    main()
