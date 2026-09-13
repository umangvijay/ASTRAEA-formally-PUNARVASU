"""MODEL-FORGE data generator: parametric SQL task pairs over a fixed demo schema.

Questions, gold SQL and expected result rows are GENERATED from templates against a real
sqlite database — every pair is verifiable (run the SQL, compare rows). The schema is
seeded-random so the combo space comfortably exceeds the requested task count (the old
tiny schema could not produce enough unique questions — a real bug this phase caught).
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass

NAMES = ["Asha", "Ravi", "Meera", "John", "Sara", "Arjun", "Priya", "Vikram", "Neha",
         "Karan", "Divya", "Rohit", "Anjali", "Sameer", "Tara", "Nikhil", "Pooja",
         "Amit", "Sneha", "Rahul"]
CITIES = ["Mumbai", "Delhi", "Goa", "Pune", "Jaipur", "Kochi"]
ITEMS = ["laptop", "phone", "monitor", "headset", "keyboard", "mouse", "tablet", "printer"]
STATUSES = ["shipped", "pending", "cancelled"]


@dataclass
class SqlTask:
    question: str
    gold_sql: str
    expected_rows: list[list]


def _seeded_data(seed: int = 99):
    rng = random.Random(seed)
    customers = []
    for i, name in enumerate(NAMES, start=1):
        customers.append((i, name, rng.choice(CITIES),
                          f"2024-{rng.randint(1, 6):02d}-{rng.randint(1, 28):02d}"))
    orders = []
    oid = 1
    for cust_id, _, _, _ in customers:
        for _ in range(rng.randint(1, 4)):
            orders.append((oid, cust_id, rng.choice(ITEMS),
                           round(rng.uniform(500, 60000), 2), rng.choice(STATUSES)))
            oid += 1
    return customers, orders


def build_db() -> sqlite3.Connection:
    customers, orders = _seeded_data()
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, joined TEXT);"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, item TEXT, "
        "amount REAL, status TEXT);"
    )
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    return conn


SCHEMA_SQL = ("""CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT, joined TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, item TEXT, amount REAL, status TEXT);""")


def _rows(conn: sqlite3.Connection, sql: str) -> list[list]:
    return [list(map(str, r)) for r in conn.execute(sql).fetchall()]


def generate_tasks(n: int, seed: int = 7) -> list[SqlTask]:
    rng = random.Random(seed)
    conn = build_db()
    tasks: list[SqlTask] = []
    blueprints = [
        ("How many orders has customer {name} placed?",
         "SELECT COUNT(*) FROM orders o JOIN customers c ON o.customer_id=c.id WHERE c.name='{name}'"),
        ("What is the total amount {name} has spent?",
         "SELECT COALESCE(SUM(amount),0) FROM orders o JOIN customers c ON o.customer_id=c.id WHERE c.name='{name}'"),
        ("List the items ordered by customers from {city}.",
         "SELECT DISTINCT o.item FROM orders o JOIN customers c ON o.customer_id=c.id WHERE c.city='{city}' ORDER BY o.item"),
        ("Which customer spent the most in total? Answer with the name only.",
         "SELECT c.name FROM customers c JOIN orders o ON o.customer_id=c.id GROUP BY c.id ORDER BY SUM(o.amount) DESC LIMIT 1"),
        ("How many orders are in {status} status?",
         "SELECT COUNT(*) FROM orders WHERE status='{status}'"),
        ("What is the average order amount for {item} orders?",
         "SELECT AVG(amount) FROM orders WHERE item='{item}'"),
        ("Which city does {name} live in? Answer with the city only.",
         "SELECT city FROM customers WHERE name='{name}'"),
        ("How much did {name} spend on {item}?",
         "SELECT COALESCE(SUM(amount),0) FROM orders o JOIN customers c ON o.customer_id=c.id WHERE c.name='{name}' AND o.item='{item}'"),
        ("How many customers are from {city}?",
         "SELECT COUNT(*) FROM customers WHERE city='{city}'"),
        ("List all items ordered by {name}.",
         "SELECT DISTINCT o.item FROM orders o JOIN customers c ON o.customer_id=c.id WHERE c.name='{name}' ORDER BY o.item"),
    ]
    seen: set[str] = set()
    guard = 0
    while len(tasks) < n and guard < n * 60:
        guard += 1
        q_sql, s_sql = rng.choice(blueprints)
        params = {"name": rng.choice(NAMES), "city": rng.choice(CITIES),
                  "status": rng.choice(STATUSES), "item": rng.choice(ITEMS)}
        question = q_sql.format(**params)
        sql = s_sql.format(**params)
        if question in seen:
            continue
        try:
            rows = _rows(conn, sql)
        except sqlite3.Error:
            continue
        seen.add(question)
        tasks.append(SqlTask(question=question, gold_sql=sql, expected_rows=rows))
    if len(tasks) < n:
        raise RuntimeError(f"generator exhausted: only {len(tasks)} unique tasks possible")
    return tasks


def rows_match(a: list[list], b: list[list]) -> bool:
    norm = lambda rows: sorted(map(lambda r: tuple(str(x).strip().lower() for x in r), rows))
    return norm(a) == norm(b)


def training_jsonl(tasks: list[SqlTask]) -> list[dict]:
    return [
        {"messages": [
            {"role": "system", "content": "You write a single SQLite query. Reply with the SQL only, no prose."},
            {"role": "user", "content": f"Schema: {SCHEMA_SQL.strip()}\nQuestion: {t.question}"},
            {"role": "assistant", "content": t.gold_sql},
        ]}
        for t in tasks
    ]


def write_jsonl(path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows))
