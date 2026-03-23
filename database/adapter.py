import os

class DatabaseAdapterFactory:
    @staticmethod
    def get_database_adapter():
        db_type = os.environ.get('DB_TYPE', 'sqlite')
        if db_type == 'postgresql':
            from database.postgresql_adapter import PostgresAdapter
            return PostgresAdapter()
        else:
            from database.sqlite_adapter import SQLiteAdapter
            return SQLiteAdapter()  

# Usage
# adapter = DatabaseAdapterFactory.get_database_adapter()