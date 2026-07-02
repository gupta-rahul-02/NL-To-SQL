import pyodbc
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=MRIPF4ZBY2A;DATABASE=RMX6M_Man2;UID=PDUser;PWD=PDUser'
)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_TYPE='BASE TABLE'")
count = cur.fetchone()[0]
print(f"Tables in dbo: {count}")

# Also show first 10 table names
cur.execute("SELECT TOP 10 TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
print("Sample tables:")
for row in cur.fetchall():
    print(" ", row[0])
conn.close()
