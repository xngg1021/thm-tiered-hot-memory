#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
THM — 分层热交换记忆体系 · 换页策略引擎
依据: docs/01-研究综述.md 公理2(ACT-R激活)、公理7(间隔重校验)、公理8(干扰控制)

用法:
  python thm.py seed                      # 从 MEMORY.md/USER.md 初始化 index.json(幂等)
  python thm.py audit                     # 全量审计:激活/降级/晋升/重校验/查重/排序提议
  python thm.py hit <定位子串> [备注]      # 记录一次"提取并派上用场"事件(测试效应)
  python thm.py confirm <定位子串>         # 重校验确认(推进间隔排期)
  python thm.py register <store> <子串> <high|med|low>  # 手动登记条目元数据
  python thm.py manifest                  # 打印 T1 温层清单(索引=系统的眼睛)

设计边界: 本脚本只读 MEMORY.md/USER.md 并产出"提议",从不直接修改它们——
T0 的写入通道永远是 Hermes memory 工具(注入扫描/字符预算由它保证)。
"""
import json, os, re, sys, datetime, difflib

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(BASE, "index.json")
WARM_DIR = os.path.join(BASE, "warm")
REPORTS = os.path.join(BASE, "reports")

def _default_mem_dir():
    """Profile-agnostic fallback: Hermes memories dir under the user home."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        return os.path.join(home, "AppData", "Local", "hermes", "memories")
    return os.path.join(home, ".hermes", "memories")

def _resolve_mem_dir():
    # 优先级: 环境变量 THM_MEM_DIR > 本目录 thm.conf(mem_dir=...) > default profile
    env = os.environ.get("THM_MEM_DIR")
    if env:
        return env
    conf = os.path.join(BASE, "thm.conf")
    if os.path.exists(conf):
        with open(conf, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("mem_dir"):
                    return line.split("=", 1)[1].strip()
    return _default_mem_dir()

MEM_DIR = _resolve_mem_dir()

DECAY_D = 0.5            # ACT-R 幂律衰减指数(Anderson & Schooler 1991)
W = {"hit": 2.0, "confirm": 1.5, "create": 1.0, "promote": 1.5, "demote": 0.0}
DEMOTE_A = 0.6           # T0→T1 激活阈值
DEMOTE_AGE = 21          # 且年龄需超过(天)
COLD_A = 0.3             # T1→T2 阈值
COLD_IDLE = 90
REVIEW_LADDER = [3, 7, 30, 90]   # 间隔重校验阶梯(天)

def today():
    return datetime.date.today()

def parse_store(path):
    """解析 § 分隔的记忆文件 → [(条目文本, 起始行号)]"""
    if not os.path.exists(path):
        return []
    entries, buf = [], []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            if line.strip() == "§":
                if buf:
                    entries.append((" ".join(buf).strip(), ln - len(buf)))
                    buf = []
            elif line.strip():
                buf.append(line.strip())
    if buf:
        entries.append((" ".join(buf).strip(), 0))
    return entries

def load_index():
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "entries": []}

def save_index(idx):
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)

def days_since(iso):
    try:
        return max(0, (today() - datetime.date.fromisoformat(iso)).days)
    except Exception:
        return 0

def activation(entry):
    a = 0.0
    for ev in entry.get("events", []):
        w = W.get(ev.get("type"), 1.0)
        a += w * (days_since(ev.get("t", "1970-01-01")) + 1) ** (-DECAY_D)
    return a

def find_entry(idx, needle):
    # 先直接匹配 key/summary;匹配不到则回查记忆文件全文,
    # 用命中文本的前 24 字符(key 的截取规则)反查登记条目
    hits = [e for e in idx["entries"] if needle in e.get("key", "") or needle in e.get("summary", "")]
    if hits:
        return hits
    for store in ("MEMORY.md", "USER.md"):
        for text, _ in parse_store(os.path.join(MEM_DIR, store)):
            if needle in text:
                key = text[:24]
                hits = [e for e in idx["entries"] if e.get("key") == key]
                if hits:
                    return hits
    return []

def review_advance(entry):
    """确认一次,排期沿阶梯推进一档"""
    cur = entry.get("review_stage", 0)
    nxt = min(cur + 1, len(REVIEW_LADDER) - 1)
    entry["review_stage"] = nxt
    entry["next_review"] = (today() + datetime.timedelta(days=REVIEW_LADDER[nxt])).isoformat()

def _next_id(idx):
    if not idx["entries"]:
        return "e001"
    return f"e{max(int(e['id'][1:]) for e in idx['entries']) + 1:03d}"

def cmd_seed():
    idx = load_index()
    known = {e["key"] for e in idx["entries"]}
    added = 0
    for store in ("MEMORY.md", "USER.md"):
        for text, _ in parse_store(os.path.join(MEM_DIR, store)):
            key = text[:24]
            if key in known:
                continue
            idx["entries"].append({
                "id": _next_id(idx),
                "tier": "T0", "store": store, "key": key,
                "summary": text[:60],
                "created": today().isoformat(),
                "events": [{"t": today().isoformat(), "type": "create"}],
                "cost_class": "med", "review_stage": 0,
                "next_review": (today() + datetime.timedelta(days=REVIEW_LADDER[0])).isoformat(),
            })
            known.add(key)
            added += 1
    save_index(idx)
    print(f"seed 完成: 新登记 {added} 条, 库内共 {len(idx['entries'])} 条")

def cmd_audit():
    idx = load_index()
    stores = {s: parse_store(os.path.join(MEM_DIR, s)) for s in ("MEMORY.md", "USER.md")}
    live_texts = [t for texts in stores.values() for t, _ in texts]

    print("=" * 66)
    print("THM 审计报告", today().isoformat())
    print("=" * 66)
    chars = {s: sum(len(t) for t, _ in v) for s, v in stores.items()}
    print(f"热层占用: MEMORY.md {chars['MEMORY.md']} 字符 / USER.md {chars['USER.md']} 字符")
    print(f"index.json 登记条目: {len(idx['entries'])} 条")
    print()

    # 1) 激活与降级/晋升
    print("── 激活评分(ACT-R, d=0.5)与换层提议 ──")
    demote, review_due, cold = [], [], []
    for e in idx["entries"]:
        a = activation(e)
        e["_a"] = a
        age = days_since(e.get("created", today().isoformat()))
        if e["tier"] == "T0":
            orphan = not any(e["key"][:16] in t for t in live_texts)
            if orphan:
                print(f"  [孤儿] {e['id']} key='{e['key']}…' 在记忆文件中已找不到,建议注销登记")
            if a < DEMOTE_A and age > DEMOTE_AGE and e.get("cost_class") != "high":
                demote.append((e, a, age))
        elif e["tier"] == "T1":
            last_hit = max((ev["t"] for ev in e["events"] if ev["type"] == "hit"), default=None)
            idle = days_since(last_hit) if last_hit else 999
            if a < COLD_A and idle > COLD_IDLE:
                cold.append((e, a))
        if e.get("next_review", "9999") <= today().isoformat():
            review_due.append(e)
    for e, a, age in sorted(demote, key=lambda x: x[1]):
        print(f"  [降级提议 T0→T1] A={a:.2f} age={age}d :: {e['summary']}")
    for e, a in cold:
        print(f"  [归档提议 T1→T2] A={a:.2f} :: {e['summary']}")
    if not demote and not cold:
        print("  (无降级/归档提议:热层条目激活均在阈值之上)")
    print()

    # 2) 间隔重校验到期
    print("── 间隔重校验到期(阶梯 +3/+7/+30/+90 天) ──")
    if review_due:
        for e in review_due:
            print(f"  [到期] {e['id']} 下次本应 {e['next_review']} :: {e['summary']}")
        print("  → 请逐条确认是否仍然成立; 成立则 `thm.py confirm <子串>`, 不成立则降级")
    else:
        print("  (无到期条目)")
    print()

    # 3) 干扰控制:模糊查重
    print("── 干扰控制(近似条目共存=每次检索都在付干扰税) ──")
    dups = []
    es = idx["entries"]
    for i in range(len(es)):
        for j in range(i + 1, len(es)):
            r = difflib.SequenceMatcher(None, es[i]["summary"], es[j]["summary"]).ratio()
            if r > 0.55:
                dups.append((r, es[i], es[j]))
    if dups:
        for r, a_, b_ in sorted(dups, reverse=True):
            print(f"  [疑似重复 {r:.0%}] '{a_['summary'][:30]}' ≈ '{b_['summary'][:30]}'")
    else:
        print("  (未发现近似重复)")
    print()

    # 4) 热层排序提议(首因效应:高激活靠前)
    print("── T0 排序提议(按激活降序,高激活应置于文件前部) ──")
    t0 = sorted([e for e in idx["entries"] if e["tier"] == "T0"], key=lambda e: -e["_a"])
    for rank, e in enumerate(t0[:8], 1):
        print(f"  #{rank} A={e['_a']:.2f} :: {e['summary'][:44]}")
    if len(t0) > 8:
        print(f"  … 共 {len(t0)} 条 T0")
    print()
    print("提议均不自动执行: T0 的变更请用 Hermes memory 工具批量操作。")

def cmd_hit(needle, note=""):
    idx = load_index()
    hits = find_entry(idx, needle)
    if not hits:
        print(f"未找到含 '{needle}' 的条目"); return
    e = hits[0]
    e["events"].append({"t": today().isoformat(), "type": "hit", "note": note})
    save_index(idx)
    print(f"已记录 hit: {e['id']} A→{activation(e):.2f} :: {e['summary'][:50]}")

def cmd_confirm(needle):
    idx = load_index()
    hits = find_entry(idx, needle)
    if not hits:
        print(f"未找到含 '{needle}' 的条目"); return
    e = hits[0]
    e["events"].append({"t": today().isoformat(), "type": "confirm"})
    review_advance(e)
    save_index(idx)
    print(f"已确认: {e['id']}, 下次重校验 {e['next_review']}, A→{activation(e):.2f}")

def cmd_register(store, needle, cost):
    idx = load_index()
    texts = dict(parse_store(os.path.join(MEM_DIR, store)))
    match = [t for t in texts if needle in t]
    if not match:
        print(f"{store} 中未找到含 '{needle}' 的条目"); return
    key = match[0][:24]
    if any(e["key"] == key for e in idx["entries"]):
        print("该条目已登记"); return
    idx["entries"].append({
        "id": _next_id(idx), "tier": "T0", "store": store,
        "key": key, "summary": match[0][:60], "created": today().isoformat(),
        "events": [{"t": today().isoformat(), "type": "create"}],
        "cost_class": cost, "review_stage": 0,
        "next_review": (today() + datetime.timedelta(days=REVIEW_LADDER[0])).isoformat(),
    })
    save_index(idx)
    print(f"已登记: {key}… (cost={cost})")

def cmd_manifest():
    print("T1 温层清单(warm/):")
    if not os.path.isdir(WARM_DIR):
        print("  (目录不存在)"); return
    files = [f for f in os.listdir(WARM_DIR) if f.endswith(".md")]
    if not files:
        print("  (空——首个降级提议执行后这里才会有内容)")
    for f in files:
        p = os.path.join(WARM_DIR, f)
        with open(p, encoding="utf-8") as fh:
            first = next((l.strip() for l in fh if l.strip()), "")
        print(f"  {f:<36} {os.path.getsize(p):>6}B  {first[:50]}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(0)
    cmd = args[0]
    if cmd == "seed": cmd_seed()
    elif cmd == "audit": cmd_audit()
    elif cmd == "hit": cmd_hit(args[1], " ".join(args[2:]))
    elif cmd == "confirm": cmd_confirm(args[1])
    elif cmd == "register": cmd_register(args[1], args[2], args[3])
    elif cmd == "manifest": cmd_manifest()
    else: print(__doc__)
