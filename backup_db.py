# Create a new file: backup_db.py

import os
import subprocess
from datetime import datetime
import shutil
import mysql.connector
from config import DB_CONFIG

def backup_database():
    # Configuration
    db_name = DB_CONFIG['database']
    db_user = DB_CONFIG['user']
    db_password = DB_CONFIG['password']
    db_host = DB_CONFIG['host']
    
    # Create backup directory if it doesn't exist
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f"{db_name}_{timestamp}.sql")
    
    # Build the mysqldump command
    mysqldump_cmd = [
        'mysqldump',
        f'--host={db_host}',
        f'--user={db_user}',
        f'--password={db_password}',
        '--databases', db_name,
        '--routines',  # Include stored procedures and functions
        '--triggers',  # Include triggers
        '--add-drop-table',  # Add DROP TABLE statements before CREATE TABLE
        '--single-transaction',  # For InnoDB tables
        f'--result-file={backup_file}'
    ]
    
    try:
        # Run the backup command
        subprocess.run(mysqldump_cmd, check=True)
        print(f"Backup created: {backup_file}")
        
        # Keep only the last 5 backups
        all_backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) 
                            if f.startswith(db_name) and f.endswith('.sql')])
        
        if len(all_backups) > 5:
            for old_backup in all_backups[:-5]:
                os.remove(old_backup)
                print(f"Removed old backup: {old_backup}")
        
        return True, backup_file
    except Exception as e:
        print(f"Backup failed: {e}")
        return False, str(e)

def restore_database(backup_file):
    # Configuration
    db_name = DB_CONFIG['database']
    db_user = DB_CONFIG['user']
    db_password = DB_CONFIG['password']
    db_host = DB_CONFIG['host']
    
    if not os.path.exists(backup_file):
        return False, f"Backup file does not exist: {backup_file}"
    
    try:
        # Build the mysql command to restore
        mysql_cmd = [
            'mysql',
            f'--host={db_host}',
            f'--user={db_user}',
            f'--password={db_password}'
        ]
        
        # Restore from the backup file
        with open(backup_file, 'r') as f:
            process = subprocess.Popen(mysql_cmd, stdin=f)
            process.wait()
        
        print(f"Restore completed from: {backup_file}")
        return True, "Restore completed successfully"
    except Exception as e:
        print(f"Restore failed: {e}")
        return False, str(e)

# Run backup if script is executed directly
if __name__ == "__main__":
    success, message = backup_database()
    print("Backup completed" if success else f"Backup failed: {message}")