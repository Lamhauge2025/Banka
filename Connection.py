# import oracledb
#
# # Connection details (replace with your values)
# username = 'dbbook'
# password = 'password'
# dsn = '192.168.9.176/xepdb1'  # e.g., 'localhost:1521/orcl'
#
# try:
#     # Connect to the database
#     connection = oracledb.connect(user=username, password=password, dsn=dsn)
#     print("Connected to Oracle DB successfully!")
#
#     # Example: Execute a simple query
#     cursor = connection.cursor()
#     cursor.execute("SELECT * FROM boking")
#     rows = cursor.fetchall()
#     for row in rows:
#         print(row)
#
#     # Close resources
#     cursor.close()
#     connection.close()
#     print("Connection closed.")
#
# except oracledb.Error as e:
#     print(f"Error connecting to Oracle DB: {e}")
#
