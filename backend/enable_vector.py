import psycopg2
import time

max_retries = 5
for i in range(max_retries):
    try:
        conn = psycopg2.connect("postgresql://admin:admin@localhost:5433/cctv")
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.close()
        conn.close()
        print("Vector extension enabled successfully!")
        break
    except Exception as e:
        print(f"Attempt {i+1} failed: {e}")
        time.sleep(2)
