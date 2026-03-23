import psycopg2
from psycopg2 import pool
import sqlite3
from threading import Lock

class ConnectionPool:
    def __init__(self, db_type, db_config):
        self.db_type = db_type
        self.lock = Lock()
        if db_type == 'postgresql':
            self.pool = psycopg2.pool.SimpleConnectionPool(
                minconn=db_config['minconn'],
                maxconn=db_config['maxconn'],
                user=db_config['user'],
                password=db_config['password'],
                host=db_config['host'],
                port=db_config['port'],
                database=db_config['database']
            )
        elif db_type == 'sqlite':
            self.connection_string = db_config['database']
        else:
            raise ValueError("Unsupported database type.")

    def get_connection(self):
        self.lock.acquire()
        try:
            if self.db_type == 'postgresql':
                return self.pool.getconn()
            elif self.db_type == 'sqlite':
                return sqlite3.connect(self.connection_string)
        finally:
            self.lock.release()

    def release_connection(self, connection):
        self.lock.acquire()
        try:
            if self.db_type == 'postgresql':
                self.pool.putconn(connection)
            elif self.db_type == 'sqlite':
                connection.close()
        finally:
            self.lock.release()  

# Example usage:
# postgres_pool = ConnectionPool('postgresql', {
#     'minconn': 1,
#     'maxconn': 10,
#     'user': 'your_user',
#     'password': 'your_password',
#     'host': 'localhost',
#     'port': 5432,
#     'database': 'your_database'
# })
#
# sqlite_pool = ConnectionPool('sqlite', {'database': 'your_database.db'})
