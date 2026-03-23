import psycopg2

class PgManager:
    def __init__(self, database, user, password, host='localhost', port='5432'):
        self.connection = psycopg2.connect(
            database=database,
            user=user,
            password=password,
            host=host,
            port=port
        )
        self.cursor = self.connection.cursor()

    def create_table(self, table_name, columns):
        column_definitions = ', '.join([f'{name} {ctype}' for name, ctype in columns.items()])
        create_table_query = f'CREATE TABLE {table_name} ({column_definitions});'
        self.cursor.execute(create_table_query)
        self.connection.commit()

    def insert_data(self, table_name, data):
        columns = data.keys()
        values = [data[column] for column in columns]
        insert_query = f'INSERT INTO {table_name} ({