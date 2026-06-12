import pymysql
import queue
import threading

class ConnectionPool:
    def __init__(self, host, port, user, password, database, pool_size=10):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.pool = queue.Queue(maxsize=pool_size)
        self.lock = threading.Lock()
        
        # Pre-initialize connections in the pool
        for _ in range(pool_size):
            conn = self._create_connection()
            if conn:
                self.pool.put(conn)

    def _create_connection(self):
        try:
            return pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
        except Exception as e:
            print(f"Error creating connection to database: {e}")
            return None

    def get_connection(self):
        try:
            # Try to get from pool quickly; fallback to blocking for up to 3 seconds
            conn = self.pool.get(timeout=3)
            # Ensure connection is alive; reconnect if ping fails
            try:
                conn.ping()
            except Exception:
                conn = self._create_connection()
            return conn
        except queue.Empty:
            # Fallback in case of heavy concurrent load
            return self._create_connection()

    def release_connection(self, conn):
        if conn:
            try:
                self.pool.put(conn, block=False)
            except queue.Full:
                try:
                    conn.close()
                except Exception:
                    pass

# Initialize connection pool targeting active sofi_mysql container
pool = ConnectionPool(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='sofi',
    database='sofi',
    pool_size=10
)

def query(sql, params=None):
    """
    Executes a MySQL SQL statement with optional parameters and returns
    results as a list of dict objects matching DictCursor mappings.
    """
    conn = pool.get_connection()
    if not conn:
        raise Exception("CRITICAL: Failed to acquire database connection from pool.")
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()
    except Exception as e:
        print(f"Database query error: {e}\nQuery: {sql}\nParams: {params}")
        raise e
    finally:
        pool.release_connection(conn)

# Test connectivity on module import
try:
    _conn = pool.get_connection()
    if _conn:
        print("Successfully connected to the sofi_mysql container database pool from Python.")
        pool.release_connection(_conn)
    else:
        print("CRITICAL: Failed to connect to the sofi_mysql database. Ensure the container is running and port 3306 is open.")
except Exception as _e:
    print(f"CRITICAL: Failed to connect to the sofi_mysql database. Error: {_e}")
