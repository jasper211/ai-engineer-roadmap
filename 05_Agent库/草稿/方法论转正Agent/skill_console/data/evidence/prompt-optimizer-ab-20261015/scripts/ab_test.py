#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prompt Optimizer A/B：用其上游模板（固定提交 1e1f94c）改写模块1提示词，同一候选池同一模型对照。

步骤：build → optimize → run → score，可单独执行，产物写入上级目录。
不安装 Prompt Optimizer 应用；这里复现的是它的模板 + 调用方式，不是应用本身。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
AGENT_DIR = BASE.parents[3]  # 方法论转正Agent/
sys.path.insert(0, str(AGENT_DIR))
from llm_client import call_deepseek  # noqa: E402

RUN = Path("/Users/a112233/Desktop/Jasper工作文档（不含EA项目）/项目工作区/Rw权益项目工作区/"
           "U020_月度行情热点解读/16_重构轮次_Refactor_Rounds/R04_模块1重建_热点直采_20260923/runs/2026-09")
TPL = BASE / "upstream_templates"
OUT = BASE / "outputs"
MODEL = "deepseek-v4-pro"
UNITS = {
    "international_policy": "国际金融政策",
    "domestic_financial_policy": "国内金融政策",
    "hk_insurance_regulation": "香港保监动态",
    "geopolitical_risk": "地缘政治风险",
    "economic_data": "经济数据统计",
}


def key():
    return json.loads((AGENT_DIR / "deepseek_config.json").read_text())["DEEPSEEK_API_KEY"]


def ts_content(name):
    """取 .ts 模板里 content 的反引号字符串（按出现顺序）。"""
    src = (TPL / name).read_text(encoding="utf-8")
    parts = re.findall(r"content:\s*`(.*?)`\s*(?:,|\n\s*\})", src, re.S)
    # mustache 定界符切换，渲染后即字面 {{variable_name}}
    return [p.replace("{{=<% %>=}}{{variable_name}}<%={{ }}=%>", "{{variable_name}}") for p in parts]


def build():
    """A 版：原 prompt_rendered.md 指令正文，仅替换检索节(一之二)与 HTML 节(五)及输出结构(三)为 JSON。"""
    src = (RUN / "prompt_rendered.md").read_text(encoding="utf-8")
    body = src.split("## 与上期的差异记录")[0]
    body = body.replace("请检索并产出", "请基于用户提供的候选池（已完成检索，不得再检索或引入池外信息）产出")
    sec = re.split(r"(?m)^### ", body)
    keep = {s.split("\n", 1)[0][:3]: s for s in sec[1:]}
    head = sec[0].replace("## 指令正文（以下整段可直接复制）\n\n", "")
    head = head.replace("输出为一个自包含的单文件 HTML", "输出为一个 JSON 对象")
    json_spec = """三、输出结构（JSON，不要输出其他文字）

{
  "main_lines": ["5 条，每类一条，一句话概括该类当月核心叙事"],
  "categories": [
    {
      "name": "类别名（五类之一）",
      "title": "如『香港保监动态 Top 9』，N 为实际条数",
      "keywords": ["4～6 个本月关键词"],
      "note": "仅当不足 10 条时填写：实际条数与具体原因；满 10 条时为空字符串",
      "items": [
        {"rank": 1, "date": "MM-DD 或 09-初/09-中/09-下/—", "event": "事件与概述，须含具体性锚点（数字/《文件名》/「原话」）",
         "heat": "热度依据，点到媒体名或传播形态", "url": "原文链接，必须取自候选池 reports", "cand_id": "候选编号"}
      ]
    }
  ],
  "limitations": ["数据局限声明，逐条"]
}

"""
    a = head + "### " + keep["一、分"] + "### " + keep["二、每"] + "### " + json_spec + "### " + keep["四、硬"]
    a = a.rstrip().rstrip("-").rstrip() + "\n"
    (OUT / "prompt_A_original.md").write_text(a, encoding="utf-8")
    pool = []
    for line in open(RUN / "candidates.jsonl", encoding="utf-8"):
        c = json.loads(line)
        pool.append({"cand_id": c["cand_id"], "unit": UNITS[c["unit"]], "event": c["event"],
                     "first_seen": c["first_seen"], "heat_line": c.get("heat_line", ""),
                     "event_extended": c.get("event_extended", ""),
                     "supplement": c.get("supplement", ""),
                     "reports": [{k: r.get(k) for k in ("url", "title", "date")} for r in c["reports"]]})
    (OUT / "pool.json").write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    print("A", len(a), "chars; pool", len(pool))


def optimize():
    a = (OUT / "prompt_A_original.md").read_text(encoding="utf-8")
    # B：通用优化——字符串模板作为 system，原提示词作为 user（与应用内调用方式一致）
    g = ts_content("general-optimize.ts")[0]
    b = call_deepseek(g, a, key(), model=MODEL, json_mode=False, temperature=0)
    (OUT / "prompt_B_general.md").write_text(b, encoding="utf-8")
    # C：分析式结构优化——消息数组模板，originalPrompt 以 JSON 字符串注入
    sysm, userm = ts_content("analytical-optimize.ts")
    userm = userm.replace("{{#helpers.toJson}}{{{originalPrompt}}}{{/helpers.toJson}}", json.dumps(a, ensure_ascii=False))
    c = call_deepseek(sysm, userm, key(), model=MODEL, json_mode=False, temperature=0)
    (OUT / "prompt_C_analytical.md").write_text(c, encoding="utf-8")
    print("B", len(b), "C", len(c))


def run(which):
    pool = (OUT / "pool.json").read_text(encoding="utf-8")
    for v in which:
        p = next(OUT.glob(f"prompt_{v}_*.md")).read_text(encoding="utf-8")
        user = "以下是 2026-09 已完成检索的候选池（JSON），只能从中选材，按系统指令输出 JSON：\n" + pool
        res = call_deepseek(p, user, key(), model=MODEL, json_mode=True, temperature=0, max_tokens=16000)
        (OUT / f"result_{v}.json").write_text(res, encoding="utf-8")
        print(v, len(res))


VAGUE = ("影响大", "关注度高", "影响较大", "广泛关注", "备受关注", "引发关注")
RULES = {  # 关键规则保留检查：规则名 → 任一关键词出现即视为保留
    "候选池宽口径/按侧面拆条": ["侧面", "宽口径"],
    "归期按发布日不按数据所属月": ["发布日", "披露日"],
    "日期区间09-01至09-23": ["09-23", "9月23", "09‑23"],
    "不编造/链接必须真实": ["编造"],
    "不足10条标题写实际条数": ["实际条数"],
    "不得凑数": ["凑数"],
    "同一事件不跨类重复": ["跨类", "首要属性"],
    "热度为定性排序非点击数": ["定性"],
    "排除单一公司产品类": ["产品"],
    "关税归国际/半导体归经济": ["关税"],
    "事件须含具体性锚点": ["锚点"],
}


def score():
    pool = json.loads((OUT / "pool.json").read_text(encoding="utf-8"))
    url2cand = {r["url"]: c for c in pool for r in c["reports"]}
    cand_unit = {c["cand_id"]: c["unit"] for c in pool}
    rows = []
    for v in ("A", "B", "C"):
        prompt = next(OUT.glob(f"prompt_{v}_*.md")).read_text(encoding="utf-8")
        kept = {k: any(w in prompt for w in ws) for k, ws in RULES.items()}
        r = {"版本": v, "提示词字数": len(prompt), "规则保留": f"{sum(kept.values())}/{len(kept)}",
             "丢失规则": [k for k, ok in kept.items() if not ok]}
        f = OUT / f"result_{v}.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            cats = d["categories"]
        except Exception as e:  # noqa: BLE001
            r["输出"] = f"无法解析：{e}"
            rows.append(r)
            continue
        items = [(c, it) for c in cats for it in c.get("items", [])]
        fake = [it.get("url") for _, it in items if it.get("url") not in url2cand]
        badd = [it.get("date") for _, it in items
                if not re.fullmatch(r"09-(0[1-9]|1\d|2[0-3])|09-[初中下]|—|-", str(it.get("date", "")).strip())]
        noanc = [it.get("rank") for _, it in items if not re.search(r"\d|[一二三四五六七八九十百千万亿]|《|「|“", it.get("event", ""))]
        vague = [it.get("heat") for _, it in items if any(w in it.get("heat", "") for w in VAGUE)]
        used = [it.get("cand_id") for _, it in items]
        dup = sorted({x for x in used if used.count(x) > 1})
        wrongcat = [it.get("cand_id") for c, it in items if cand_unit.get(it.get("cand_id")) not in (None, c.get("name"))]
        mism = []
        for c in cats:
            n = len(c.get("items", []))
            m = re.search(r"Top\s*(\d+)", c.get("title", ""))
            if not m or int(m.group(1)) != n or (n < 10 and not c.get("note")):
                mism.append(f'{c.get("name")}:{c.get("title")}/{n}条/note={"有" if c.get("note") else "无"}')
        r.update({"类别数": len(cats), "总条数": len(items),
                  "各类条数": {c.get("name"): len(c.get("items", [])) for c in cats},
                  "池外/编造链接": len(fake), "日期越界或格式错": len(badd), "缺锚点": len(noanc),
                  "空话热度": len(vague), "重复用同一候选": dup, "跨类错放": len(wrongcat),
                  "标题与条数/说明不符": mism, "主线条数": len(d.get("main_lines", [])),
                  "局限声明条数": len(d.get("limitations", []))})
        rows.append(r)
    (OUT / "score.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    step = sys.argv[1]
    if step == "run":
        run(sys.argv[2:] or ["A", "B", "C"])
    else:
        globals()[step]()
