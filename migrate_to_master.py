#!/usr/bin/env python3
"""
Migration script to convert existing separate CSV files to the new master CSV structure.
This script will read all existing CSV files and create a unified master CSV.
"""

import pandas as pd
import csv
import os
from datetime import datetime
import hashlib

def normalize_title(title):
    import re
    return re.sub(r'[^\w\s]', '', title).strip().lower()

def normalize_simple_firstlast(name):
    import unicodedata
    name = unicodedata.normalize('NFKD', name)
    words = [w for w in name.replace(",", " ").split() if w]
    if not words:
        return ""
    if len(words) == 1:
        return words[0].lower()
    return (words[0] + " " + words[-1]).lower()

def generate_paper_id(title, first_author):
    norm_title = normalize_title(title)
    norm_author = normalize_simple_firstlast(first_author)
    combined = norm_title + norm_author
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def migrate_csv_files():
    """Migrate all existing CSV files to master CSV"""
    
    master_data = []
    
    # Files to migrate with their corresponding status
    files_to_migrate = [
        ('declined_papers.csv', 'declined'),
        ('optioned_papers.csv', 'optioned'),
        ('solicited_papers.csv', 'solicited'),
        ('solicited_accepted.csv', 'accepted'),
        ('solicited_declined.csv', 'declined')
    ]
    
    for filename, status in files_to_migrate:
        if os.path.exists(filename):
            print(f"Migrating {filename} to status '{status}'...")
            
            try:
                df = pd.read_csv(filename)
                
                for _, row in df.iterrows():
                    # Extract data based on available columns
                    title = row.get('title', '')
                    first_author = row.get('first_author', '')
                    authors = row.get('authors', '')
                    journal = row.get('journal', '')
                    affiliations = row.get('affiliations', '')
                    
                    # Generate paper ID if not present
                    paper_id = row.get('paper_id', '')
                    if not paper_id and title and first_author:
                        paper_id = generate_paper_id(title, first_author)
                    
                    # Convert authors string to list
                    authors_list = [a.strip() for a in authors.split(';') if a.strip()] if authors else []
                    
                    # Convert affiliations string to list
                    affiliations_list = [a.strip() for a in affiliations.split(';') if a.strip()] if affiliations else []
                    
                    # Create master record
                    master_record = {
                        'paper_id': paper_id,
                        'title': title,
                        'first_author': first_author,
                        'authors': '; '.join(authors_list),
                        'journal': journal,
                        'affiliations': '; '.join(affiliations_list),
                        'norm_title': normalize_title(title),
                        'norm_first_author': normalize_simple_firstlast(first_author),
                        'status': status,
                        'date_added': datetime.now().isoformat(),
                        'date_updated': datetime.now().isoformat()
                    }
                    
                    master_data.append(master_record)
                    
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue
    
    # Create master CSV
    if master_data:
        master_df = pd.DataFrame(master_data)
        
        # Remove duplicates based on paper_id
        master_df = master_df.drop_duplicates(subset=['paper_id'], keep='first')
        
        # Sort by date_added
        master_df = master_df.sort_values('date_added', ascending=False)
        
        # Save to master CSV
        master_df.to_csv('papers_master.csv', index=False)
        print(f"Successfully created papers_master.csv with {len(master_df)} papers")
        
        # Show summary
        print("\nMigration Summary:")
        status_counts = master_df['status'].value_counts()
        for status, count in status_counts.items():
            print(f"- {status}: {count} papers")
    else:
        print("No data found to migrate.")

def backup_existing_files():
    """Create backups of existing CSV files"""
    import shutil
    from datetime import datetime
    
    backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    files_to_backup = [
        'declined_papers.csv',
        'optioned_papers.csv', 
        'solicited_papers.csv',
        'solicited_accepted.csv',
        'solicited_declined.csv'
    ]
    
    for filename in files_to_backup:
        if os.path.exists(filename):
            shutil.copy2(filename, os.path.join(backup_dir, filename))
            print(f"Backed up {filename} to {backup_dir}/")
    
    return backup_dir

if __name__ == "__main__":
    print("PCG Dashboard CSV Migration Tool")
    print("=" * 40)
    
    # Check if master CSV already exists
    if os.path.exists('papers_master.csv'):
        response = input("papers_master.csv already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled.")
            exit()
    
    # Create backup
    print("\nCreating backup of existing files...")
    backup_dir = backup_existing_files()
    
    # Perform migration
    print("\nStarting migration...")
    migrate_csv_files()
    
    print(f"\nMigration complete! Backup files are in: {backup_dir}")
    print("\nYou can now use the improved app with the master CSV structure.") 