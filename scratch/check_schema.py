import sqlite3

conn = sqlite3.connect("data/pychronicle.db")
row = conn.execute("SELECT sql FROM sqlite_master WHERE name='programs' AND type='table';").fetchone()
print("Programs SQL:", row[0] if row else "None")
