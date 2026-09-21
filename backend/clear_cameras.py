import psycopg2

conn = psycopg2.connect("postgresql://admin:admin@localhost:5433/cctv")
cur = conn.cursor()
cur.execute("DELETE FROM cameras;")
conn.commit()
cur.execute("SELECT count(*) FROM cameras;")
print(f"Cameras remaining: {cur.fetchone()[0]}")
cur.close()
conn.close()
print("All stale camera entries cleared.")
