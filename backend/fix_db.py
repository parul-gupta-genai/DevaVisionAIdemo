import psycopg2

conn = psycopg2.connect("postgresql://admin:admin@localhost:5433/cctv")
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE cameras ADD COLUMN state VARCHAR DEFAULT 'STOPPED';")
except psycopg2.errors.DuplicateColumn:
    conn.rollback()
else:
    conn.commit()

try:
    cur.execute("ALTER TABLE cameras ADD COLUMN edge_id VARCHAR DEFAULT 'edge-01';")
except psycopg2.errors.DuplicateColumn:
    conn.rollback()
else:
    conn.commit()

cur.close()
conn.close()
print("Database schema successfully patched.")
