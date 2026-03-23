import psycopg2
from psycopg2 import pool

class DatabaseManager:
    def __init__(self, minconn, maxconn, db_name, user, password, host='localhost', port='5432'):
        self.connection_pool = pool.SimpleConnectionPool(
            minconn,
            maxconn,
            database=db_name,
            user=user,
            password=password,
            host=host,
            port=port
        )

    def get_connection(self):
        """Get a connection from the pool"""
        return self.connection_pool.getconn()

    def release_connection(self, connection):
        """Release a connection back to the pool"""
        self.connection_pool.putconn(connection)

    def close_all_connections(self):
        """Close all connections in the pool"""
        self.connection_pool.closeall()

# Example usage
# db_manager = DatabaseManager(1, 10, 'mydb', 'user', 'password')
# conn = db_manager.get_connection()
# db_manager.release_connection(conn)