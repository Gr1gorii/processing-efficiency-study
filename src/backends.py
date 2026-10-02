"""Three deliberately simple implementations with one result contract."""

from collections import defaultdict
import sqlite3

FACT_COLUMNS = ["id", "customer_id", "category_id", "amount_cents", "status"]
CUSTOMER_COLUMNS = ["customer_id", "segment_id"]


class PythonBackend:
    def __init__(self, fact, customers):
        self.fact = fact.tolist()
        self.customers = dict(customers.tolist())

    def execute(self, operation):
        if operation == "filter":
            return sorted((r[0], r[3]) for r in self.fact
                          if r[4] == 1 and r[3] >= 5000)
        groups = defaultdict(lambda: [0, 0])
        for row in self.fact:
            if operation == "group":
                key = row[2]
            elif operation == "join":
                if row[1] not in self.customers:
                    continue
                key = self.customers[row[1]]
            else:
                raise ValueError(operation)
            groups[key][0] += 1
            groups[key][1] += row[3]
        return [(key, *groups[key]) for key in sorted(groups)]

    def close(self):
        pass


class PandasBackend:
    def __init__(self, fact, customers):
        import pandas as pd
        self.fact = pd.DataFrame(fact, columns=FACT_COLUMNS, copy=False)
        self.customers = pd.DataFrame(customers, columns=CUSTOMER_COLUMNS, copy=False)

    def execute(self, operation):
        if operation == "filter":
            selected = self.fact.loc[
                (self.fact["status"] == 1) & (self.fact["amount_cents"] >= 5000),
                ["id", "amount_cents"],
            ].sort_values("id")
            return list(selected.itertuples(index=False, name=None))
        if operation == "group":
            table, key = self.fact, "category_id"
        elif operation == "join":
            table = self.fact.merge(self.customers, on="customer_id", how="inner")
            key = "segment_id"
        else:
            raise ValueError(operation)
        grouped = table.groupby(key, sort=True)["amount_cents"].agg(["size", "sum"])
        return list(grouped.reset_index().itertuples(index=False, name=None))

    def close(self):
        pass


class SQLiteBackend:
    def __init__(self, fact, customers):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA threads=1")
        self.connection.execute("PRAGMA temp_store=MEMORY")
        self.connection.execute("CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, segment_id INTEGER)")
        self.connection.execute("CREATE TABLE fact (id INTEGER, customer_id INTEGER, category_id INTEGER, amount_cents INTEGER, status INTEGER)")
        self.connection.executemany("INSERT INTO customers VALUES (?, ?)", customers.tolist())
        # Bounded chunks avoid a second million-row Python list during insertion.
        for start in range(0, len(fact), 10000):
            self.connection.executemany("INSERT INTO fact VALUES (?, ?, ?, ?, ?)",
                                        fact[start:start + 10000].tolist())
        self.connection.commit()

    def execute(self, operation):
        queries = {
            "filter": "SELECT id, amount_cents FROM fact WHERE status = 1 AND amount_cents >= 5000 ORDER BY id",
            "group": "SELECT category_id, COUNT(*), SUM(amount_cents) FROM fact GROUP BY category_id ORDER BY category_id",
            "join": "SELECT c.segment_id, COUNT(*), SUM(f.amount_cents) FROM fact f INNER JOIN customers c ON f.customer_id = c.customer_id GROUP BY c.segment_id ORDER BY c.segment_id",
        }
        return self.connection.execute(queries[operation]).fetchall()

    def close(self):
        self.connection.close()


BACKENDS = {"python": PythonBackend, "pandas": PandasBackend, "sqlite": SQLiteBackend}
