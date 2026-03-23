import contextlib
import sqlite3

class TransactionHandler:
    def __init__(self, db_name):
        self.db_name = db_name

    @contextlib.contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.db_name)
        try:
            yield conn
            conn.commit()  # Commit changes on exit
        except Exception:
            conn.rollback()  # Rollback on exception
            raise
        finally:
            conn.close()  # Close connection

    @contextlib.contextmanager
    def savepoint(self, savepoint_name):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute(f'SAVEPOINT {savepoint_name};')
        try:
            yield cursor
            conn.commit()  # Commit changes on exit
        except Exception:
            cursor.execute(f'ROLLBACK TO {savepoint_name};')  # Rollback to savepoint on exception
            raise
        finally:
            conn.close()  # Close connection

# Example usage
# with TransactionHandler('my_database.db').transaction() as conn:
#     conn.execute("INSERT INTO my_table (column) VALUES ('value')")
# 
# with TransactionHandler('my_database.db').savepoint('my_savepoint') as cursor:
#     cursor.execute("INSERT INTO my_table (column) VALUES ('value')")
