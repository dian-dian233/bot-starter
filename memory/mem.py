#!/usr/bin/env python3
"""点点的事实型记忆库：抽取 -> 覆盖 -> 带时间 -> 可检索。

设计取舍：
  * 只存"事实三元组"(subject, predicate, value) + 作用域 + 来源 + 时间
  * 同一 (scope, subject, predicate) 只保留一条有效记录，新的自动让旧的作废
  * 检索用多关键词 LIKE 打分，不引向量库；中文实体（人名/域名）靠关键词更准
"""
import argparse, json, os, sqlite3, sys
from datetime import datetime, timezone

DB = os.environ.get("MEM_DB", os.path.expanduser("~/dd-home/mem/mem.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS mem(
  id INTEGER PRIMARY KEY,
  scope TEXT NOT NULL,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL,
  value TEXT NOT NULL,
  confidence REAL DEFAULT 0.8,
  source TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  superseded_by INTEGER
);
CREATE INDEX IF NOT EXISTS ix_mem_slot ON mem(scope, subject, predicate, valid_to);
CREATE INDEX IF NOT EXISTS ix_mem_subject ON mem(subject);
"""

def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c

def fmt(r):
    tag = "" if r["valid_to"] is None else f"  [已作废 {r['valid_to']}]"
    return f"#{r['id']:<4} [{r['scope']}] {r['subject']} · {r['predicate']} = {r['value']}{tag}\n      ↳ 来源 {r['source']} | 有效自 {r['valid_from']}"

def cmd_add(a):
    c = conn(); ts = now()
    cur = c.execute("SELECT id FROM mem WHERE scope=? AND subject=? AND predicate=? AND valid_to IS NULL",
                    (a.scope, a.subject, a.predicate)).fetchall()
    for r in cur:  # 覆盖：旧记录作废，指向新记录
        pass
    new_id = None
    if cur:
        # 先插入新记录，再把旧的指过去
        c.execute("INSERT INTO mem(scope,subject,predicate,value,confidence,source,created_at,updated_at,valid_from) VALUES(?,?,?,?,?,?,?,?,?)",
                  (a.scope, a.subject, a.predicate, a.value, a.confidence, a.source, ts, ts, ts))
        new_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        for r in cur:
            c.execute("UPDATE mem SET valid_to=?, superseded_by=?, updated_at=? WHERE id=?", (ts, new_id, ts, r["id"]))
        print(f"已覆盖 #{cur[0]['id']} -> #{new_id}")
    else:
        c.execute("INSERT INTO mem(scope,subject,predicate,value,confidence,source,created_at,updated_at,valid_from) VALUES(?,?,?,?,?,?,?,?,?)",
                  (a.scope, a.subject, a.predicate, a.value, a.confidence, a.source, ts, ts, ts))
        new_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        print(f"已记住 #{new_id}")
    c.commit()
    print(fmt(c.execute("SELECT * FROM mem WHERE id=?", (new_id,)).fetchone()))

def cmd_get(a):
    c = conn()
    q = "SELECT * FROM mem WHERE scope=? AND subject=? AND predicate=? AND valid_to IS NULL"
    r = c.execute(q, (a.scope, a.subject, a.predicate)).fetchone()
    print(fmt(r) if r else "（没有这条记忆）")

def cmd_search(a):
    c = conn()
    terms = [t for t in a.query.split() if t]
    if not terms:
        return
    where = " AND ".join(["(subject LIKE ? OR predicate LIKE ? OR value LIKE ?)"] * len(terms))
    params = []
    for t in terms:
        params += [f"%{t}%"] * 3
    if not a.all:
        where += " AND valid_to IS NULL"
    rows = c.execute(f"SELECT * FROM mem WHERE {where}", params).fetchall()
    def score(r):
        blob = f"{r['subject']}{r['predicate']}{r['value']}"
        return (sum(t in blob for t in terms), r["updated_at"])
    rows = sorted(rows, key=score, reverse=True)[: a.limit]
    if a.json:
        print(json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2)); return
    if not rows: print("（没检索到）")
    for r in rows: print(fmt(r))

def cmd_list(a):
    c = conn()
    sql = "SELECT * FROM mem WHERE valid_to IS NULL"
    p = ()
    if a.scope: sql += " AND scope=?"; p = (a.scope,)
    rows = c.execute(sql + " ORDER BY updated_at DESC", p).fetchall()
    print(f"有效记忆 {len(rows)} 条")
    for r in rows: print(fmt(r))

def cmd_history(a):
    c = conn()
    rows = c.execute("SELECT * FROM mem WHERE subject=? AND predicate=? ORDER BY valid_from", (a.subject, a.predicate)).fetchall()
    for r in rows: print(fmt(r))

def cmd_forget(a):
    c = conn(); ts = now()
    c.execute("UPDATE mem SET valid_to=?, updated_at=? WHERE id=? AND valid_to IS NULL", (ts, ts, a.id))
    c.commit(); print(f"已作废 #{a.id}")

def cmd_stats(a):
    c = conn()
    cur = c.execute("SELECT COUNT(*) FROM mem WHERE valid_to IS NULL").fetchone()[0]
    old = c.execute("SELECT COUNT(*) FROM mem WHERE valid_to IS NOT NULL").fetchone()[0]
    scopes = c.execute("SELECT scope, COUNT(*) n FROM mem WHERE valid_to IS NULL GROUP BY scope").fetchall()
    print(f"有效 {cur} / 历史 {old}")
    for r in scopes: print(f"  {r['scope']}: {r['n']}")

p = argparse.ArgumentParser(prog="mem")
sub = p.add_subparsers(dest="cmd", required=True)

a1 = sub.add_parser("add"); a1.add_argument("subject"); a1.add_argument("predicate"); a1.add_argument("value")
a1.add_argument("--scope", default="group"); a1.add_argument("--source", default="chat"); a1.add_argument("--confidence", type=float, default=0.8)
a1.set_defaults(fn=cmd_add)

a2 = sub.add_parser("get"); a2.add_argument("subject"); a2.add_argument("predicate"); a2.add_argument("--scope", default="group")
a2.set_defaults(fn=cmd_get)

a3 = sub.add_parser("search"); a3.add_argument("query"); a3.add_argument("--limit", type=int, default=8)
a3.add_argument("--all", action="store_true"); a3.add_argument("--json", action="store_true")
a3.set_defaults(fn=cmd_search)

a4 = sub.add_parser("list"); a4.add_argument("--scope"); a4.set_defaults(fn=cmd_list)
a5 = sub.add_parser("history"); a5.add_argument("subject"); a5.add_argument("predicate"); a5.set_defaults(fn=cmd_history)
a6 = sub.add_parser("forget"); a6.add_argument("id", type=int); a6.set_defaults(fn=cmd_forget)
a7 = sub.add_parser("stats"); a7.set_defaults(fn=cmd_stats)

args = p.parse_args()
args.fn(args)
