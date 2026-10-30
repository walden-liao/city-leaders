"""清理原始抓取数据，输出前端使用的 data.json。

用法：python3 tools/clean_data.py
输入：tools/data_raw.json（原始抓取结果，不手改）
输出：data.json（站点根目录）
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "tools" / "data_raw.json"
OUT = ROOT / "data.json"

# 2026-10-30 底表复核指出以下原 C 类证据不足；保留原始数据，生成时撤回判断。
UNVERIFIED_FISCAL = set("芜湖 蚌埠 遵义 成都 秦皇岛 邯郸 沧州 运城 忻州 赤峰 巴彦淖尔 铜陵 池州 湛江 儋州 攀枝花 淄博".split())

# 抓取时误识别为人名的词，整条丢弃。多数来自正文括号被拆开，如 国防动员（人防）
JUNK_NAMES = {"取正文", "栏目", "应急管理", "白干酿酒", "工商联"}
JUNK_NAME_RE = re.compile(
    r"工作|管理|动员|供销|集团|正文|商会|人防|委员|政府|方面|公司|中心|研究|大学|指挥部|机构|事务"
    r"|健康|旅游|文化|农业|农村|商务|外事|外办|国动|金融|财税|党校|拆迁|民政|水利|能源|林业|烟草"
    r"|驻穗|港口|逐人|上一版|版本|后续|片段|补充|通知|转载|索到|秘书长|全面|华侨|山东|中国|山农"
    r"|统战|文旅|文艺|组织部|数据|信访|卫生|财政|商务|口岸|外|部$|局$|社$|联$"
)
# 分工文本里混入的抓取备注，从这些位置起整段删除
NOTE_RE = re.compile(
    r"\s#|——\s*http|\s-\s*https?:|【体例|（另有|另有20|另据上一版|百度百科|故.{0,6}记「|若官方网站"
    r"|未定位到|以上仅用于|https?://|\s【|（协助分管记录"
)
FRAGMENT_RE = re.compile(r"^[、，,；;。…]")
# 原始分工文本按固定长度截取，达到这个长度视为被截断
TRUNC_LEN = 415

stats = Counter()


def clean_name(n):
    n = re.sub(r"同志$", "", n.strip())
    if len(n) < 2:
        stats["name_unrecognized"] += 1
        return "姓名未识别"
    return n


def clean_title(t):
    t = re.split(r"[，,]\s*(?=页|另有)", t.strip())[0]
    if re.search(r"WAF|另有|页面|更新", t):
        stats["title_cleared"] += 1
        return ""
    return t


def cut_bleed(d, me, others):
    """分工文本串入了后面其他人的分工时，在下一个人名处切断。

    只认人名后紧跟括号、冒号或同志的位置，避免误切协助某某市长这类正文。
    """
    cut = len(d)
    for n in others:
        if n == me:
            continue
        m = re.search(re.escape(n) + r"(同志)?[（(：:]", d)
        if m and 3 < m.start() < cut:
            cut = m.start()
    return d[:cut].rstrip(" ；;，,"), cut < len(d)


def clean_city(x):
    if x["f"] == "未查到":
        x["f"], x["fm"] = "不明确", "分工页不全"
        stats["fiscal_relabel"] += 1

    # 部分市的班子人数只记了市长 1 人或为 0，用副职人数加市长补正
    if x["nl"] in ("0", "1"):
        nv = int(x["nv"]) if x["nv"].isdigit() else 0
        x["nl"] = str(nv + 1) if nv else ""
        if not nv:
            x["nv"] = ""
        stats["team_size_fixed"] += 1

    pp = []
    for p in x["pp"]:
        n = re.sub(r"同志$", "", p["n"].strip())
        m = re.match(r"([\u4e00-\u9fa5]{2,3})\s", p.get("t", ""))
        if n == "秘书长" and m:
            p = {**p, "n": m.group(1), "t": "秘书长"}
            n = m.group(1)
            stats["secretary_recovered"] += 1
        if n in JUNK_NAMES or JUNK_NAME_RE.search(n) or "WAF" in p.get("t", ""):
            stats["junk_dropped"] += 1
            continue
        pp.append(p)

    names = [clean_name(p["n"]) for p in pp]
    out = []
    for p, n in zip(pp, names):
        raw_d = p.get("d", "").strip()
        item = {"n": n, "t": clean_title(p.get("t", "")), "a": bool(p.get("a"))}
        starts_with_other = any(
            re.match(re.escape(o) + r"(同志)?[（(：:]", raw_d) for o in names if o != n
        )
        if FRAGMENT_RE.match(raw_d) or starts_with_other:
            item["d"] = ""
            stats["duty_unrecognized"] += 1
            out.append(item)
            continue
        d, was_cut = cut_bleed(raw_d, n, names)
        m = NOTE_RE.search(d)
        if m:
            d = d[: m.start()].rstrip(" ；;，,（(")
            was_cut = True
            stats["note_removed"] += 1
        d = re.sub(r"^(分工\s+|【[^】]{2,6}】)", "", d)
        if len(d) <= 2:
            d = ""
            stats["duty_unrecognized"] += 1
        item["d"] = d
        if was_cut:
            stats["bleed_cut"] += 1
        elif len(raw_d) >= TRUNC_LEN:
            item["x"] = 1
            stats["truncated"] += 1
        out.append(item)
    x["pp"] = out
    return x


def main():
    data = json.loads(RAW.read_text(encoding="utf-8"))
    data = [clean_city(x) for x in data]
    for x in data:
        if x['c'].removesuffix('市') in UNVERIFIED_FISCAL:
            x.update(f='不明确', fm='分工待核实', o='', mf='未明确')
        if x['c'] == '岳阳市':
            x.update(f='E', fm='其他变体', o='常务副市长协助分管财政', mf='未明确',
                     u='https://www.yueyang.gov.cn/ldjs/70888/content_2169050.html', v='')
    reviews = {r['city']: r for r in json.loads((ROOT / 'tools/fiscal_reviews.json').read_text(encoding='utf-8'))}
    for x in data:
        if x['c'] in reviews:
            r = reviews[x['c']]
            if x['f'] != r['after']:
                raise ValueError(f"分类与修订记录不一致：{x['c']}")
            x['review'] = r
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data)} 个市，写入 {OUT}")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
