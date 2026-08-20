#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT_JS = ROOT / "data" / "live-policies.js"
OUT_META = ROOT / "data" / "live-meta.json"
TZ_CN = timezone(timedelta(hours=8))

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
})

# 只允许中央权威政府网站
ALLOWED_HOSTS = {
    "www.gov.cn", "gov.cn",
    "www.ndrc.gov.cn", "ndrc.gov.cn", "zfxxgk.ndrc.gov.cn",
    "www.nea.gov.cn", "nea.gov.cn", "zfxxgk.nea.gov.cn",
    "www.mee.gov.cn", "mee.gov.cn",
}

# 权威来源入口
SOURCE_PAGES = [
    ("生态环境部", "https://www.mee.gov.cn/zcwj/"),
    ("生态环境部", "https://www.mee.gov.cn/zcwj/bwj/wj/"),
    ("生态环境部", "https://www.mee.gov.cn/zcwj/bwj/gg/"),
    ("生态环境部", "https://www.mee.gov.cn/zcwj/bgtwj/wj/"),

    ("国家发展改革委", "https://www.ndrc.gov.cn/xxgk/zcfb/tz/index.html"),
    ("国家发展改革委", "https://www.ndrc.gov.cn/xxgk/zcfb/ghxwj/index.html"),
    ("国家发展改革委", "https://www.ndrc.gov.cn/xxgk/wjk/index.html"),

    ("国家能源局", "https://www.nea.gov.cn/"),
    ("国家能源局", "https://zfxxgk.nea.gov.cn/"),

    ("国务院/中国政府网", "https://www.gov.cn/zhengce/"),
]

# 最终入库必须命中至少一个“碳主题强关键词”
CORE_TERMS = [
    # 碳市场
    "全国碳排放权交易市场", "全国碳市场", "碳排放权交易", "碳市场",
    "碳排放配额", "配额清缴", "重点排放单位", "碳交易",

    # CCER / 自愿减排
    "温室气体自愿减排", "核证自愿减排", "国家核证自愿减排量",
    "自愿减排交易", "自愿减排项目", "CCER",

    # 双碳 / 碳排放管理
    "碳达峰", "碳中和", "双碳", "碳排放双控", "碳排放总量",
    "碳排放强度", "碳排放核算", "碳排放管理", "二氧化碳排放",
    "节能降碳", "减污降碳",

    # 温室气体 / 气候变化
    "温室气体排放", "温室气体清单", "企业温室气体排放",
    "应对气候变化", "国家自主贡献",

    # 绿电绿证
    "绿色电力证书", "绿证", "绿色电力交易", "绿电交易",
    "绿电直连", "绿色电力消费", "绿电消费", "非化石能源电力消费",
]

# 列表页先用更宽的词做候选，详情页再严格过滤
CANDIDATE_TERMS = CORE_TERMS + [
    "可再生能源", "非化石能源", "新型能源体系", "绿色低碳",
    "能源绿色转型", "低碳", "方法学", "排放核算", "能源消费",
]

NOISE_TERMS = [
    "危险废物", "新化学物质", "排污许可证", "水污染物", "土壤污染",
    "地下水污染", "海洋倾倒", "核安全", "放射性污染", "环境影响报告",
    "生态文明奖", "科技活动周", "实验室", "工程技术中心",
]

DATE_RE = re.compile(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})")
DOC_RE = re.compile(
    r"((?:国发|国办发|发改[\u4e00-\u9fa5]*|环[\u4e00-\u9fa5]*|国能[\u4e00-\u9fa5]*|公告)"
    r"[〔\[]20\d{2}[〕\]][^\s，。；]{0,20}号)"
)

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def contains_any(text, terms):
    u = (text or "").upper()
    return any(x.upper() in u for x in terms)

def norm_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"

def allowed_url(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)

def is_candidate(title, context=""):
    return contains_any(f"{title} {context}", CANDIDATE_TERMS)

def is_final_relevant(title, body):
    text = f"{title} {body}"
    if not contains_any(text, CORE_TERMS):
        return False
    if contains_any(text, NOISE_TERMS) and not contains_any(title, CORE_TERMS):
        return False
    return True

def classify(text):
    if contains_any(text, ["CCER","温室气体自愿减排","核证自愿减排","国家核证自愿减排量","自愿减排交易","自愿减排项目"]):
        return "CCER政策"
    if contains_any(text, ["全国碳排放权交易市场","全国碳市场","碳排放权交易","碳排放配额","配额清缴","重点排放单位","碳交易"]):
        return "全国碳市场"
    if contains_any(text, ["绿色电力证书","绿证","绿色电力交易","绿电交易","绿电直连","绿色电力消费","绿电消费","非化石能源电力消费"]):
        return "绿电绿证"
    if contains_any(text, ["碳达峰","碳中和","双碳","碳排放双控","碳排放总量","碳排放强度","碳排放核算","碳排放管理","二氧化碳排放","节能降碳","减污降碳"]):
        return "双碳/碳排放管理"
    return "气候变化/温室气体"

def market_for(category):
    return {
        "CCER政策": "CCER",
        "全国碳市场": "全国CEA",
        "绿电绿证": "绿电/绿证",
        "双碳/碳排放管理": "双碳政策",
        "气候变化/温室气体": "气候政策",
    }[category]

def agency_from_url(url):
    host = (urlparse(url).hostname or "").lower()
    if "ndrc.gov.cn" in host: return "国家发展改革委"
    if "nea.gov.cn" in host: return "国家能源局"
    if "mee.gov.cn" in host: return "生态环境部"
    if "gov.cn" in host: return "国务院/中国政府网"
    return host

def source_priority(url, category):
    host = (urlparse(url).hostname or "").lower()
    if category in ("全国碳市场", "CCER政策"):
        order = ["mee.gov.cn", "gov.cn", "ndrc.gov.cn", "nea.gov.cn"]
    elif category == "绿电绿证":
        order = ["ndrc.gov.cn", "nea.gov.cn", "gov.cn", "mee.gov.cn"]
    else:
        order = ["gov.cn", "ndrc.gov.cn", "nea.gov.cn", "mee.gov.cn"]
    for i, d in enumerate(order):
        if host == d or host.endswith("." + d):
            return i
    return 99

def fetch(url):
    r = session.get(url, timeout=25)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def page_variants(url, n=6):
    seen = set()
    variants = [url]
    for i in range(1, n):
        if url.endswith("/"):
            variants += [urljoin(url, f"index_{i}.shtml"), urljoin(url, f"index_{i}.html")]
        elif url.endswith("index.html"):
            variants += [url.replace("index.html", f"index_{i}.html"),
                         url.replace("index.html", f"index_{i}.shtml")]
    for v in variants:
        if v not in seen:
            seen.add(v)
            yield v

def discover_candidates():
    found = {}
    for label, base in SOURCE_PAGES:
        for page_url in page_variants(base):
            try:
                html = fetch(page_url)
            except Exception as e:
                print("listing skip:", page_url, str(e)[:80])
                continue
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                title = clean(a.get_text(" ", strip=True))
                if len(title) < 6:
                    continue
                href = urljoin(page_url, a["href"])
                if not allowed_url(href):
                    continue
                context = clean(a.parent.get_text(" ", strip=True) if a.parent else "")
                if not is_candidate(title, context):
                    continue
                found[href] = {
                    "title": title,
                    "source_url": href,
                    "listing_date": norm_date(context),
                    "discovered_from": label,
                }
            time.sleep(0.12)
    return list(found.values())

def meta_content(soup, names):
    for name in names:
        t = soup.find("meta", attrs={"name": name})
        if t and t.get("content"): return clean(t["content"])
        t = soup.find("meta", attrs={"property": name})
        if t and t.get("content"): return clean(t["content"])
    return ""

def parse_detail(item):
    try:
        html = fetch(item["source_url"])
    except Exception as e:
        print("detail skip:", item["source_url"], str(e)[:80])
        return None

    soup = BeautifulSoup(html, "html.parser")
    body = clean(soup.get_text("\n", strip=True))
    title = meta_content(soup, ["ArticleTitle", "og:title"]) or item["title"]
    title = re.sub(r"[-_—|].*(?:中国政府网|国家发展和改革委员会|国家能源局|生态环境部).*?$", "", title).strip()
    if not is_final_relevant(title, body[:14000]):
        return None

    category = classify(f"{title} {body[:10000]}")
    date = norm_date(meta_content(soup, ["PubDate","pubDate","publishdate","date"])) or item["listing_date"] or norm_date(body[:2500])

    dm = DOC_RE.search(body[:6000])
    doc = clean(dm.group(1)) if dm else ""

    publisher = agency_from_url(item["source_url"])
    for pat in [
        r"发布机关[:：\s]*([^\n]{2,80}?)(?=生成日期|成文日期|发布日期|文号|文\s*号|$)",
        r"主办单位[:：\s]*([^\n]{2,80}?)(?=制发日期|索引号|$)",
        r"发文机关[:：\s]*([^\n]{2,80}?)(?=成文日期|发布日期|$)",
    ]:
        m = re.search(pat, body[:5000])
        if m:
            p = clean(m.group(1))
            if 2 <= len(p) <= 80:
                publisher = p
                break

    desc = meta_content(soup, ["description","Description"])
    if desc and "中华人民共和国" not in desc:
        summary = desc[:180]
    else:
        positions = [body.find(k) for k in CORE_TERMS if body.find(k) >= 0]
        pos = min(positions) if positions else max(0, body.find(title))
        excerpt = body[max(0,pos-100):pos+900]
        sentences = [clean(x) for x in re.split(r"[。！？]", excerpt) if 18 <= len(clean(x)) <= 260]
        summary = (sentences[0] if sentences else title)[:180]

    industries = [k for k in ["发电","钢铁","水泥","铝冶炼","石化","化工","建材","有色","建筑","交通","农业","林业","能源","电力","数据中心"] if k in body[:14000]]
    if not industries: industries = ["综合"]

    stable_id = int(hashlib.sha1(item["source_url"].encode()).hexdigest()[:10], 16)
    return {
        "id": stable_id,
        "date": date,
        "title": title,
        "doc": doc,
        "publisher": publisher,
        "category": category,
        "status": "征求意见" if "征求意见" in title else "有效",
        "market": market_for(category),
        "summary": summary,
        "source_url": item["source_url"],
        "source_agency": agency_from_url(item["source_url"]),
        "scope": ["全国"],
        "industries": industries,
        "parameters": [["结构化状态","待后续提取关键参数"]],
        "compliance": [["执行节点","待后续提取履约节点"]],
        "impact": "政策事实来自权威政府网站；市场影响需结合真实交易数据计算。",
    }

def deduplicate(records):
    by_title = {}
    for r in records:
        key = re.sub(r"[\s《》（）()，,。:：\-—]", "", r["title"])
        old = by_title.get(key)
        if old is None or source_priority(r["source_url"], r["category"]) < source_priority(old["source_url"], old["category"]):
            by_title[key] = r
    return list(by_title.values())

def main():
    candidates = discover_candidates()
    print("candidate links:", len(candidates))
    records = []
    for i, item in enumerate(candidates, 1):
        r = parse_detail(item)
        if r: records.append(r)
        if i % 15 == 0: time.sleep(0.2)

    records = deduplicate(records)
    records.sort(key=lambda x: (x.get("date") or "0000-00-00", x["title"]), reverse=True)

    source_names = sorted(set(r["source_agency"] for r in records))
    meta = {
        "generated_at": datetime.now(TZ_CN).isoformat(timespec="seconds"),
        "source_label": "权威碳政策",
        "source_count": len(source_names),
        "sources": source_names,
        "policy_count": len(records),
        "mode": "live-carbon-filtered",
        "topics": ["全国碳市场","CCER/自愿减排","双碳/碳排放","绿电绿证","气候变化/温室气体"],
    }

    OUT_JS.parent.mkdir(parents=True, exist_ok=True)
    OUT_JS.write_text(
        "window.LIVE_POLICY_META = " + json.dumps(meta, ensure_ascii=False, indent=2) + ";\n" +
        "window.LIVE_POLICIES = " + json.dumps(records, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8"
    )
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", len(records), "carbon-related policies")
    print("sources:", ", ".join(source_names))

if __name__ == "__main__":
    main()
