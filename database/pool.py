import sqlite3
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import threading

class ConnectionPoolManager:
    def __init__(self, db_type, db_config):
        self.db_type = db_type
        self.db_config = db_config
        self.connection_pool = None
        self.lock = threading.Lock()
        self.connection_stats = {'total_connections': 0, 'active_connections': 0}

        if db_type == 'sqlite':
            self._initialize_sqlite_pool()
        elif db_type == 'postgresql':
            self._initialize_postgresql_pool()
        else:
            raise ValueError("Unsupported database type. Please use 'sqlite' or 'postgresql'.")

    def _initialize_sqlite_pool(self):
        self.connection_pool = sqlite3.connect(self.db_config['database'])
        self.connection_stats['total_connections'] += 1

    def _initialize_postgresql_pool(self):
        self.connection_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=self.db_config.get('minconn', 1),
            maxconn=self.db_config.get('maxconn', 10),
            user=self.db_config['user'],
            password=self.db_config['password'],
            host=self.db_config['host'],
            port=self.db_config['port'],
            database=self.db_config['database'])
        # Increment total connection count for PostgreSQL initialization
        self.connection_stats['total_connections'] += self.connection_pool.numavailable + self.connection_pool.numinuse

    @contextmanager
    def get_connection(self):
        if self.db_type == 'sqlite':
            conn = self.connection_pool
        elif self.db_type == 'postgresql':
            conn = self.connection_pool.getconn()
        else:
            raise ValueError("Unsupported database type.")

        with self.lock:
            self.connection_stats['active_connections'] += 1
            try:
                yield conn
            finally:
                if self.db_type == 'postgresql':
                    self.connection_pool.putconn(conn)
                self.connection_stats['active_connections'] -= 1

    def get_connection_stats(self):
        return self.connection_stats

    def close_all_connections(self):
        if self.db_type == 'postgresql':
            self.connection_pool.closeall()
        elif self.db_type == 'sqlite':
            self.connection_pool.close()  # Close SQLite connection

# Example Configuration for SQLite
# db_config_sqlite = { 'database': 'mydb.sqlite' }

# Example Configuration for PostgreSQL
# db_config_postgresql = { 'user': 'username', 'password': 'password', 'host': 'localhost', 'port': 5432, 'database': 'mydb' }