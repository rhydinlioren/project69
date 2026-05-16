import subprocess
import sys
import os
import shutil
import zipfile
import json
import time
from datetime import datetime
import hashlib

# Auto-install dependencies
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

for pkg, imp in [
    ("boto3",     "boto3"),
    ("colorama",  "colorama"),
]:
    try:
        __import__(imp)
    except ImportError:
        print(f"{pkg} not found. Installing...")
        install_package(pkg)

import boto3
from botocore.exceptions import ClientError
from colorama import init, Fore, Style

init(autoreset=True)

# Header
ASCII_HEADER = """
░█▀▄░█▀█░█▀▀░█░█░█░█░█▀█░█▄█░█▀▀░░░█░█░▀▀█
░█▀▄░█▀█░█░░░█▀▄░█░█░█▀▀░█░█░█░░░░░▀▄▀░░▀▄
░▀▀░░▀░▀░▀▀▀░▀░▀░▀▀▀░▀░░░▀░▀░▀▀▀░░░░▀░░▀▀░
"""

def print_header(subtitle=""):
    print(f"{Fore.WHITE}{ASCII_HEADER}{Style.DIM}")
    if subtitle:
        print(f"{Fore.YELLOW}  {subtitle}")
    print()

# Paths 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, 'backup_settings.json')
DOTENV_FILE   = os.path.join(BASE_DIR, '.env')

TEMP_BACKUP_PATH  = os.path.join(BASE_DIR, 'tmp_backup')
TEMP_RESTORE_PATH = os.path.join(BASE_DIR, 'tmp_restore')

# Gradient colours 
gradient_colors = [
    Fore.LIGHTYELLOW_EX, Fore.YELLOW, Fore.LIGHTGREEN_EX, Fore.GREEN,
    Fore.LIGHTCYAN_EX, Fore.CYAN, Fore.LIGHTRED_EX, Fore.RED
]

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_gradient_text(text):
    gradient_text = ""
    for i, char in enumerate(text):
        color = gradient_colors[i % len(gradient_colors)]
        gradient_text += f"{color}{char}"
    print(gradient_text)

# Settings 
DEFAULT_SETTINGS = {
    'BUCKET_NAME': '',
    'ENDPOINT': '',
    'SERVER_FOLDER_PATH': '',
    'WORLD_FOLDERS': ['world', 'world_nether', 'world_the_end'],
    'PLUGINS_FOLDER': 'plugins',
    'ADDITIONAL_FILES': [],
    'MAX_BACKUPS_TO_KEEP': 3
}

if not os.path.exists(SETTINGS_FILE):
    settings = dict(DEFAULT_SETTINGS)
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)
else:
    with open(SETTINGS_FILE, 'r') as f:
        settings = json.load(f)
    for k, v in DEFAULT_SETTINGS.items():
        settings.setdefault(k, v)

BUCKET_NAME         = settings['BUCKET_NAME']
ENDPOINT            = settings['ENDPOINT']
SERVER_FOLDER_PATH  = settings['SERVER_FOLDER_PATH']
WORLD_FOLDERS       = settings['WORLD_FOLDERS']
PLUGINS_FOLDER      = settings['PLUGINS_FOLDER']
ADDITIONAL_FILES    = settings['ADDITIONAL_FILES']
MAX_BACKUPS_TO_KEEP = settings['MAX_BACKUPS_TO_KEEP']

def _save_settings():
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

# load .env (no extra dependency) 
def load_dotenv(path):
    if not os.path.exists(path):
        return
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

load_dotenv(DOTENV_FILE)

# Credentials (env only) 
def get_credentials():
    key_id = os.environ.get("B2_KEY_ID", "").strip()
    app_key = os.environ.get("B2_APPLICATION_KEY", "").strip()
    if key_id and app_key:
        return key_id, app_key

    clear_screen()
    print_header("Initial Setup")
    print(f"{Fore.CYAN}Enter your Backblaze B2 credentials.")
    print(f"{Fore.CYAN}These will be kept in environment variables or optional .env file.\n")

    key_id = input(f"{Fore.MAGENTA}Enter your B2 KEY ID: {Style.RESET_ALL}").strip()
    app_key = input(f"{Fore.MAGENTA}Enter your B2 APPLICATION KEY: {Style.RESET_ALL}").strip()

    save = input(f"{Fore.YELLOW}Save to .env for future use? (y/N): {Style.RESET_ALL}").strip().lower()
    if save == 'y':
        with open(DOTENV_FILE, 'w') as f:
            f.write(f"B2_KEY_ID={key_id}\n")
            f.write(f"B2_APPLICATION_KEY={app_key}\n")
        print(f"{Fore.GREEN}.env saved to {DOTENV_FILE}")

    os.environ["B2_KEY_ID"] = key_id
    os.environ["B2_APPLICATION_KEY"] = app_key
    return key_id, app_key

KEY_ID, APPLICATION_KEY = get_credentials()

# B2 client 
_s3 = None

def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client(
            's3',
            endpoint_url=ENDPOINT,
            aws_access_key_id=KEY_ID,
            aws_secret_access_key=APPLICATION_KEY,
        )
    return _s3

# Bucket setup
def first_time_bucket_setup():
    global BUCKET_NAME, ENDPOINT
    clear_screen()
    print_header("Bucket Setup")
    BUCKET_NAME = input(f"{Fore.YELLOW}Enter B2 Bucket Name: {Style.RESET_ALL}").strip()
    ENDPOINT = input(f"{Fore.YELLOW}Enter B2 S3 Endpoint (e.g. https://s3.us-east-005.backblazeb2.com): {Style.RESET_ALL}").strip()

    settings['BUCKET_NAME'] = BUCKET_NAME
    settings['ENDPOINT'] = ENDPOINT
    _save_settings()
    time.sleep(1)

# Folder setup 
def first_time_folder_setup():
    global SERVER_FOLDER_PATH
    clear_screen()
    print_header("Folder Setup")
    print(f"{Fore.CYAN}1. Use THIS DIRECTORY (where the script is located)")
    print(f"{Fore.CYAN}2. Select a custom directory")
    choice = input(f"{Fore.YELLOW}Enter your choice: {Style.RESET_ALL}").strip()

    if choice == '1':
        SERVER_FOLDER_PATH = BASE_DIR
        print(f"{Fore.GREEN}Using THIS directory: {SERVER_FOLDER_PATH}")
    elif choice == '2':
        custom_folder = input(f"{Fore.YELLOW}Enter the full path to the directory: {Style.RESET_ALL}").strip()
        if os.path.isdir(custom_folder):
            SERVER_FOLDER_PATH = custom_folder
            print(f"{Fore.GREEN}Using custom directory: {SERVER_FOLDER_PATH}")
        else:
            print(f"{Fore.RED}Invalid path! Using THIS directory.")
            SERVER_FOLDER_PATH = BASE_DIR
    else:
        print(f"{Fore.RED}Invalid choice. Using THIS directory.")
        SERVER_FOLDER_PATH = BASE_DIR

    settings['SERVER_FOLDER_PATH'] = SERVER_FOLDER_PATH
    _save_settings()
    time.sleep(2)

# Checkups
if not SERVER_FOLDER_PATH:
    first_time_folder_setup()
if not BUCKET_NAME or not ENDPOINT:
    first_time_bucket_setup()

# Upload with progress

class ProgressCallback:
    def __init__(self, file_name, file_size):
        self.file_name  = file_name
        self.file_size  = file_size
        self.uploaded   = 0
        self.start_time = time.time()
        self.last_speed_str = ""

    def __call__(self, bytes_amount):
        self.uploaded += bytes_amount
        elapsed = time.time() - self.start_time
        speed   = self.uploaded / elapsed if elapsed > 0 else 0
        pct     = int(self.uploaded / self.file_size * 100) if self.file_size else 100

        if speed >= 1_048_576:
            speed_str = f"{speed / 1_048_576:.1f} MB/s"
        else:
            speed_str = f"{speed / 1024:.1f} KB/s"

        self.last_speed_str = speed_str
        print(f'\r  {self.file_name}: {pct}% — {speed_str}', end='', flush=True)
        
def format_size(size_bytes):
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.2f} GB"
    elif size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.2f} MB"
    return f"{size_bytes / 1024:.2f} KB"

def md5_of_file(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def upload_to_b2(file_path, object_key):
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    try:
        local_md5 = md5_of_file(file_path)
        callback = ProgressCallback(file_name, file_size)
        s3().upload_file(file_path, BUCKET_NAME, object_key, Callback=callback)

        response = s3().head_object(Bucket=BUCKET_NAME, Key=object_key)
        remote_md5 = response['ETag'].strip('"')

        speed = callback.last_speed_str
        if '-' in remote_md5:
            remote_size = response['ContentLength']
            if remote_size == file_size:
                print(f"\r{Fore.WHITE}  {file_name}: 100% — {speed} {Fore.GREEN}— verified ✓ (md5)")
            else:
                print(f"\r{Fore.WHITE}  {file_name}: 100% — {speed} {Fore.RED}— SIZE MISMATCH!")
        else:
            if local_md5 == remote_md5:
                print(f"\r{Fore.WHITE}  {file_name}: 100% — {speed} {Fore.GREEN}— verified ✓ (md5)")
            else:
                print(f"\r{Fore.WHITE}  {file_name}: 100% — {speed} {Fore.RED}— CHECKSUM MISMATCH!")

    except Exception as e:
        import traceback
        traceback.print_exc()

# List / Download / Delete 
def list_backup_folders():
    paginator = s3().get_paginator('list_objects_v2')
    folders = set()
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix='backups/', Delimiter='/'):
        for cp in page.get('CommonPrefixes', []):
            prefix = cp.get('Prefix', '')
            if prefix.startswith('backups/'):
                folder = prefix.replace('backups/', '').strip('/')
                if folder:
                    folders.add(folder)
    return sorted(folders)

def list_backup_files_in_folder(folder_name):
    prefix = f'backups/{folder_name}/'
    response = s3().list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
    contents = response.get('Contents', [])
    return [obj['Key'] for obj in contents if obj['Key'] != prefix]

def download_from_b2(object_key, dest_folder):
    os.makedirs(dest_folder, exist_ok=True)
    file_name = os.path.basename(object_key)
    dest_path = os.path.join(dest_folder, file_name)

    file_size = s3().head_object(Bucket=BUCKET_NAME, Key=object_key)['ContentLength']
    callback  = ProgressCallback(file_name, file_size)

    s3().download_file(BUCKET_NAME, object_key, dest_path, Callback=callback)
    print(f"\r{Fore.GREEN}Download of {file_name} completed.                 ")
    return dest_path

def delete_b2_objects(object_keys):
    if not object_keys:
        return
    chunks = [object_keys[i:i+1000] for i in range(0, len(object_keys), 1000)]
    for chunk in chunks:
        resp = s3().delete_objects(
            Bucket=BUCKET_NAME,
            Delete={'Objects': [{'Key': k} for k in chunk]}
        )
        errors = resp.get('Errors', [])
        if errors:
            print(f"{Fore.RED}Some deletes failed:")
            for err in errors:
                print(f"  - {err.get('Key')}: {err.get('Code')} {err.get('Message')}")
        else:
            print(f"{Fore.GREEN}Deleted {len(chunk)} object(s).")

def delete_all_versions_for_prefix(prefix):
    paginator = s3().get_paginator('list_object_versions')
    to_delete = []

    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for v in page.get('Versions', []):
            to_delete.append({'Key': v['Key'], 'VersionId': v['VersionId']})
        for v in page.get('DeleteMarkers', []):
            to_delete.append({'Key': v['Key'], 'VersionId': v['VersionId']})

    if not to_delete:
        print(f"{Fore.YELLOW}No versions found for {prefix}")
        return

    for i in range(0, len(to_delete), 1000):
        chunk = to_delete[i:i+1000]
        resp = s3().delete_objects(Bucket=BUCKET_NAME, Delete={'Objects': chunk})
        errors = resp.get('Errors', [])
        if errors:
            print(f"{Fore.RED}Some deletes failed:")
            for err in errors:
                print(f"  - {err.get('Key')} ({err.get('VersionId')}): {err.get('Code')} {err.get('Message')}")
        else:
            print(f"{Fore.YELLOW}Deleted {len(chunk)} version(s).")

# Zip helpers 
def zip_folder(folder_path, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, folder_path)
                zipf.write(file_path, arcname=relative_path)

def zip_additional_files(additional_files, zip_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in additional_files:
            item_path = os.path.join(SERVER_FOLDER_PATH, item)
            if os.path.isdir(item_path):
                for root, _, files in os.walk(item_path):
                    for file in files:
                        fp = os.path.join(root, file)
                        zipf.write(fp, arcname=os.path.relpath(fp, SERVER_FOLDER_PATH))
            elif os.path.exists(item_path):
                zipf.write(item_path, arcname=os.path.basename(item_path))
            else:
                print(f"{Fore.RED}Warning: {item} does not exist.")

# Extraction helpers 
def extract_directly(zip_path, destination_folder):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(destination_folder)
    print(f"{Fore.GREEN}Extraction completed successfully.")

def extract_zip_to_named_folder(zip_path, destination_folder):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        extract_folder = os.path.join(destination_folder, os.path.splitext(os.path.basename(zip_path))[0])
        os.makedirs(extract_folder, exist_ok=True)
        zip_ref.extractall(extract_folder)

def extract_specific_content(zip_path, destination_folder):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        print(f"{Fore.CYAN}Files in the archive:")
        file_list = zip_ref.namelist()
        for i, file in enumerate(file_list):
            print(f"{Fore.BLUE}{i + 1}. {file}")
        file_choice = input(f"{Fore.GREEN}Enter the number of the file to extract: {Style.RESET_ALL}").strip()
        file_choice = int(file_choice) - 1
        if file_choice < 0 or file_choice >= len(file_list):
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(2)
            return
        zip_ref.extract(file_list[file_choice], destination_folder)
        print(f"{Fore.GREEN}Restored {file_list[file_choice]} successfully.")

def copy_backup_directly(zip_path, destination_folder):
    shutil.copy(zip_path, destination_folder)
    print(f"{Fore.GREEN}Backup copied to the server folder successfully.")

# Backup retention 
def enforce_max_backups():
    global MAX_BACKUPS_TO_KEEP
    folders = list_backup_folders()

    def parse_dt(name):
        try:
            return datetime.strptime(name, "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            return None

    dated = [(f, parse_dt(f)) for f in folders]
    dated.sort(key=lambda x: (x[1] is None, x[1]))  # None dates last
    if MAX_BACKUPS_TO_KEEP <= 0:
        return
    to_delete = dated[:-MAX_BACKUPS_TO_KEEP]
    for folder, _ in to_delete:
        delete_all_versions_for_prefix(f"backups/{folder}/")

# Timezone
def get_timezone_abbr():
    return time.tzname[1] if time.daylight else time.tzname[0]

# Main actions 
def start_backup():
    clear_screen()
    print_header()
    print(f"{Fore.CYAN}Starting backup process...")

    os.makedirs(TEMP_BACKUP_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + f"_{get_timezone_abbr()}"
    backup_prefix = f"backups/{timestamp}"
    backup_start = time.time()

    try:
        for world_folder in WORLD_FOLDERS:
            src_path = os.path.join(SERVER_FOLDER_PATH, world_folder)
            dest_zip = os.path.join(TEMP_BACKUP_PATH, f'{world_folder}.zip')
            zip_folder(src_path, dest_zip)
            print(f"Zipped {world_folder}")

        plugins_src = os.path.join(SERVER_FOLDER_PATH, PLUGINS_FOLDER)
        plugins_zip = os.path.join(TEMP_BACKUP_PATH, 'plugins.zip')
        zip_folder(plugins_src, plugins_zip)
        print("Zipped plugins folder")

        if ADDITIONAL_FILES:
            add_zip = os.path.join(TEMP_BACKUP_PATH, 'AdditionalFiles.zip')
            zip_additional_files(ADDITIONAL_FILES, add_zip)
            print("Zipped additional files")

        print(f"{Fore.CYAN}Uploading to Backblaze B2...")
        total_size = 0
        for fname in os.listdir(TEMP_BACKUP_PATH):
            fpath = os.path.join(TEMP_BACKUP_PATH, fname)
            if os.path.isfile(fpath):
                total_size += os.path.getsize(fpath)
                upload_to_b2(fpath, f'{backup_prefix}/{fname}')

        print(f"{Fore.CYAN}Total uploaded: {format_size(total_size)}")

        enforce_max_backups()
        elapsed = time.time() - backup_start
        print(f"{Fore.GREEN}Backup completed in {elapsed:.1f}s")

    except Exception as e:
        print(f"{Fore.RED}Backup failed: {e}")
        time.sleep(4)

    finally:
        shutil.rmtree(TEMP_BACKUP_PATH, ignore_errors=True)
        input("Press Enter to return to the main menu...")

def list_backups():
    clear_screen()
    print_header("List Backups")
    print()
    folders = list_backup_folders()
    if not folders:
        print(f"{Fore.RED}No backups found.")
        input("\nPress Enter to return to the main menu...")
        return

    total_all = 0
    for folder in folders:
        files = list_backup_files_in_folder(folder)
        folder_size = 0
        for key in files:
            obj = s3().head_object(Bucket=BUCKET_NAME, Key=key)
            folder_size += obj['ContentLength']
        total_all += folder_size
        print(f"{Fore.CYAN}{folder}  {Fore.YELLOW}{format_size(folder_size)}")
        for key in files:
            obj = s3().head_object(Bucket=BUCKET_NAME, Key=key)
            print(f"  {Fore.BLUE}• {os.path.basename(key)}  {Fore.WHITE}{format_size(obj['ContentLength'])}")
        print()

    print(f"{Fore.CYAN}{'─' * 40}")
    print(f"{Fore.CYAN}Total used: {Fore.YELLOW}{format_size(total_all)}")
    input(f"\n{Fore.YELLOW}Press Enter to return to the main menu...")

def restore_backup():
    while True:
        try:
            clear_screen()
            print_header("Restore Backup")
            folders = list_backup_folders()

            if not folders:
                print(f"{Fore.RED}No backups found.")
                time.sleep(2)
                return

            print(f"{Fore.CYAN}Available backup folders:")
            for i, f in enumerate(folders):
                print(f"{Fore.BLUE}{i+1}. {f}")
            print(f"{Fore.BLUE}x. Exit")

            choice = input(f"{Fore.YELLOW}Select a backup folder: {Style.RESET_ALL}").strip()
            if choice.lower() == 'x':
                return

            idx = int(choice) - 1
            if idx < 0 or idx >= len(folders):
                print(f"{Fore.RED}Invalid choice.")
                time.sleep(2)
                return

            folder = folders[idx]
            files = list_backup_files_in_folder(folder)

            if not files:
                print(f"{Fore.RED}No files found in this backup.")
                time.sleep(2)
                return

            print(f"{Fore.CYAN}Files in {folder}:")
            for i, k in enumerate(files):
                print(f"{Fore.BLUE}{i+1}. {os.path.basename(k)}")
            print(f"{Fore.BLUE}a. Restore ALL files in this dated backup")
            print(f"{Fore.BLUE}x. Exit")

            file_choice = input(f"{Fore.YELLOW}Select a file to restore: {Style.RESET_ALL}").strip().lower()
            if file_choice == 'x':
                return

            if file_choice == 'a':
                selected = files
            else:
                fidx = int(file_choice) - 1
                if fidx < 0 or fidx >= len(files):
                    print(f"{Fore.RED}Invalid choice.")
                    time.sleep(2)
                    return
                selected = [files[fidx]]

            print(f"{Fore.CYAN}Select restore option:")
            print(f"{Fore.BLUE}1. Extract directly to the server folder")
            print(f"{Fore.BLUE}2. Extract to archive name with replace")
            print(f"{Fore.BLUE}3. Extract specific content into the server folder")
            print(f"{Fore.BLUE}4. Skip extraction and copy directly to the server folder")
            print(f"{Fore.BLUE}x. Exit")

            restore_choice = input(f"{Fore.GREEN}Enter your choice: {Style.RESET_ALL}").strip()
            if restore_choice.lower() == 'x':
                return

            for object_key in selected:
                print(f"{Fore.CYAN}Downloading {os.path.basename(object_key)}...")
                backup_local_path = download_from_b2(object_key, TEMP_RESTORE_PATH)

                if restore_choice == '1':
                    extract_directly(backup_local_path, SERVER_FOLDER_PATH)
                elif restore_choice == '2':
                    extract_zip_to_named_folder(backup_local_path, SERVER_FOLDER_PATH)
                elif restore_choice == '3':
                    extract_specific_content(backup_local_path, SERVER_FOLDER_PATH)
                elif restore_choice == '4':
                    copy_backup_directly(backup_local_path, SERVER_FOLDER_PATH)
                else:
                    print(f"{Fore.RED}Invalid choice.")
                    time.sleep(2)
                    return

            print(f"{Fore.GREEN}Restore completed successfully.")

        except Exception as e:
            print(f"{Fore.RED}An error occurred: {e}")
            time.sleep(4)
            return
        finally:
            shutil.rmtree(TEMP_RESTORE_PATH, ignore_errors=True)
            input("Press Enter to return to the main menu...")

def delete_backups():
    try:
        clear_screen()
        print_header("Delete Backup")

        folders = list_backup_folders()
        if not folders:
            print(f"{Fore.RED}No backups found.")
            time.sleep(2)
            return

        print(f"{Fore.CYAN}Available backup folders:")
        for i, f in enumerate(folders):
            print(f"{Fore.BLUE}{i+1}. {f}")
        print(f"{Fore.BLUE}x. Exit")

        choice = input(f"{Fore.YELLOW}Select a backup folder: {Style.RESET_ALL}").strip()
        if choice.lower() == 'x':
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(folders):
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(2)
            return

        folder = folders[idx]
        files = list_backup_files_in_folder(folder)

        print(f"{Fore.CYAN}Delete options:")
        print(f"{Fore.BLUE}1. Delete ENTIRE dated backup folder (all versions)")
        print(f"{Fore.BLUE}2. Delete specific file(s) inside this folder (all versions)")
        print(f"{Fore.BLUE}x. Exit")

        action = input(f"{Fore.YELLOW}Choose: {Style.RESET_ALL}").strip().lower()
        if action == 'x':
            return

        if action == '1':
            delete_all_versions_for_prefix(f"backups/{folder}/")
            print(f"{Fore.GREEN}Deleted backup folder: {folder}")
        elif action == '2':
            for i, k in enumerate(files):
                print(f"{Fore.BLUE}{i+1}. {os.path.basename(k)}")
            to_delete = input(f"{Fore.YELLOW}Enter numbers to delete (comma separated): {Style.RESET_ALL}").strip()
            idxs = []
            for part in to_delete.split(','):
                part = part.strip()
                if part.isdigit():
                    idxs.append(int(part) - 1)
            selected = [files[i] for i in idxs if 0 <= i < len(files)]

            for key in selected:
                delete_all_versions_for_prefix(key)

            print(f"{Fore.GREEN}Deleted selected files (all versions).")
        else:
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(2)

    except Exception as e:
        print(f"{Fore.RED}An error occurred: {e}")
        time.sleep(4)
    finally:
        input("Press Enter to return to the main menu...")

def manage_settings():
    while True:
        clear_screen()
        print_header("Manage Settings")
        print(f"{Fore.CYAN}1. Add/Remove Folder/Files (to backup)")
        print(f"{Fore.CYAN}2. Change B2 Credentials (env/.env)")
        print(f"{Fore.CYAN}3. Change Server Directory") 

        print(f"{Fore.CYAN}4. Set Max Backups To Keep")

        print(f"{Fore.CYAN}5. Change Bucket / Endpoint")

        print(f"{Fore.CYAN}x. Exit to menu")
        
        choice = input(f"{Fore.YELLOW}Enter your choice: {Style.RESET_ALL}").strip()

        if choice == '1':
            print(f"{Fore.CYAN}Current additional files/folders: {ADDITIONAL_FILES}")
            item = input(f"{Fore.YELLOW}Enter the file/folder name to add or remove: {Style.RESET_ALL}").strip()
            if item in ADDITIONAL_FILES:
                ADDITIONAL_FILES.remove(item)
                print(f"{Fore.RED}Removed {item}.")
            else:
                ADDITIONAL_FILES.append(item)
                print(f"{Fore.GREEN}Added {item}.")
            settings['ADDITIONAL_FILES'] = ADDITIONAL_FILES
            _save_settings()
            input("Press Enter to continue...")

        elif choice == '2':
            global KEY_ID, APPLICATION_KEY, _s3
            KEY_ID = input(f"{Fore.MAGENTA}Enter new B2 KEY ID: {Style.RESET_ALL}").strip()
            APPLICATION_KEY = input(f"{Fore.MAGENTA}Enter new B2 APPLICATION KEY: {Style.RESET_ALL}").strip()
            save = input(f"{Fore.YELLOW}Save to .env for future use? (y/N): {Style.RESET_ALL}").strip().lower()
            if save == 'y':
                with open(DOTENV_FILE, 'w') as f:
                    f.write(f"B2_KEY_ID={KEY_ID}\n")
                    f.write(f"B2_APPLICATION_KEY={APPLICATION_KEY}\n")
                print(f"{Fore.GREEN}.env saved to {DOTENV_FILE}")
            os.environ["B2_KEY_ID"] = KEY_ID
            os.environ["B2_APPLICATION_KEY"] = APPLICATION_KEY
            _s3 = None
            print(f"{Fore.GREEN}Credentials updated.")
            input("Press Enter to continue...")

        elif choice == '3':
            first_time_folder_setup()

        elif choice == '4':
            global MAX_BACKUPS_TO_KEEP
            val = input(f"{Fore.YELLOW}Enter max backups to keep (0 = unlimited): {Style.RESET_ALL}").strip()
            if val.isdigit():
                MAX_BACKUPS_TO_KEEP = int(val)
                settings['MAX_BACKUPS_TO_KEEP'] = MAX_BACKUPS_TO_KEEP
                _save_settings()
                print(f"{Fore.GREEN}Max backups set to {MAX_BACKUPS_TO_KEEP}")
            else:
                print(f"{Fore.RED}Invalid value.")
            input("Press Enter to continue...")

        elif choice == '5':
            first_time_bucket_setup()

        elif choice.lower() == 'x':
            return
        else:
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(2)

def main_menu():
    while True:
        clear_screen()
        print_header()
        print(f"{Fore.CYAN}1. Start Backup")
        print(f"{Fore.CYAN}2. Restore Backups")
        print(f"{Fore.CYAN}3. Delete Backups")
        print(f"{Fore.CYAN}4. Manage Settings")
        print(f"{Fore.CYAN}5. List Backups")
        print(f"{Fore.CYAN}x. Exit")

        choice = input(f"{Fore.YELLOW}Enter your choice: {Style.RESET_ALL}").strip()

        if choice == '1':
            start_backup()
        elif choice == '2':
            restore_backup()
        elif choice == '3':
            delete_backups()
        elif choice == '4':
            manage_settings()
        elif choice == '5':
            list_backups()
        elif choice.lower() == 'x':
            clear_screen()
            print(f"{Fore.GREEN}Goodbye!")
            time.sleep(2)
            break
        else:
            print(f"{Fore.RED}Invalid choice.")
            time.sleep(2)

if __name__ == '__main__':
    if settings.get('MAX_BACKUPS_TO_KEEP', None) is None:
        val = input("Enter max backups to keep (0 = unlimited): ").strip()
        if val.isdigit():
            settings['MAX_BACKUPS_TO_KEEP'] = int(val)
            _save_settings()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "1":
            start_backup()
        elif command == "2":
            restore_backup()
        elif command == "3":
            delete_backups()
        elif command == "4":
            manage_settings()
        elif command == "5":
            list_backups()
        elif command.lower() == "x":
            clear_screen()
            print(f"{Fore.GREEN}Goodbye!")
            time.sleep(2)
            sys.exit(0)
        else:
            print(f"{Fore.RED}Invalid argument.")
            print(f"{Fore.CYAN}Options: 1 (Backup)  2 (Restore)  3 (Delete)  4 (Settings)  5 (List Backups) x (Exit)")
            sys.exit(1)
    else:
        main_menu()
