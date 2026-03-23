import os
import sys

class MigrationManager:
    def __init__(self, migration_dir='migrations'):
        self.migration_dir = migration_dir
        self.migrations = []
        self.load_migrations()

    def load_migrations(self):
        try:
            files = os.listdir(self.migration_dir)
            for file in files:
                if file.endswith('.py') and file != '__init__.py':
                    version = file[:-3]  # remove '.py' to get version
                    self.migrations.append(version)
        except FileNotFoundError:
            print(f'Migration directory {self.migration_dir} not found.')

    def apply_migration(self, version):
        if version in self.migrations:
            print(f'Applying migration: {version}')
            # Load and execute the migration script
            migration_file = os.path.join(self.migration_dir, f'{version}.py')
            exec(open(migration_file).read())
        else:
            print(f'Migration version {version} does not exist.')

    def get_migration_versions(self):
        return self.migrations

if __name__ == '__main__':
    manager = MigrationManager()
    if len(sys.argv) > 1:
        manager.apply_migration(sys.argv[1])
    else:
        print('Available migrations:')
        print(manager.get_migration_versions())
