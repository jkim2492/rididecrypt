from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad
from shutil import rmtree
from bs4 import BeautifulSoup
from pprint import pprint
import os
import glob
import zipfile
import hashlib
import json
import requests
import browser_cookie3
import sys

APPDATA = os.getenv("APPDATA")
LIBRARY_PATH = Rf"{APPDATA}\Ridibooks\library"
settings = {}


def get_device_id():
    api_url = "https://account.ridibooks.com/api/user-devices/app"
    print("Device id not found. Attempting to detect device id...")
    try:
        cj = browser_cookie3.chrome()
    except:
        try:
            cj = browser_cookie3.firefox()
        except:
            print("Unable to import cookies from browsers")
            print(f"Please visit {api_url} to manually retrieve device_id")
            print("and add it to settings.json")
            quit()
    api_response = requests.get(api_url, cookies=cj)
    print(api_response.status_code)
    if str(api_response.status_code) != "200":
        print("Unable to authenticate with Ridibooks")
        print("Please ensure that you are signed in at https://ridibooks.com")
        quit()
    api_json = api_response.json()["user_devices"]
    if len(api_json) > 1:
        print("Multiple devices found. Please manually add the device_id to settings.json")
        pprint(api_json)
        quit()
    elif len(api_json) == 1:
        device_id = api_json[0]["device_id"]
        print(f"device_id: {device_id}")
        return device_id
    else:
        print("No device_id found. Is ridibooks installed on this machine?")
        quit()

def list_usercodes():
    directory_list = glob.glob(f"{LIBRARY_PATH}\\*\\")
    usercode_list = [os.path.basename(d[:-1])[1:] for d in directory_list]
    return usercode_list


def get_usercode():
    return list_usercodes()[0][0:]


def get_key(device_id, dat_path):
    short_device_id = device_id[:16]

    with open(dat_path, "rb") as rf:
        iv = rf.read(16)
        ciphertext = rf.read()

    cipher = AES.new(short_device_id.encode(), AES.MODE_CBC, bytes(iv))
    plaintext = cipher.decrypt(pad(ciphertext, 16))
    return plaintext[68:84]


def rmf(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)


def parse_metadata(decrypted_dir=""):
    opf_path = os.path.join(decrypted_dir, "OEBPS", "content.opf")
    with open(opf_path, errors="ignore", encoding="utf-8") as rf:
        content = rf.read()
    soup = BeautifulSoup(content, features="xml")
    return soup


def list_files(dir_path):
    pattern = os.path.join(dir_path, "**", "*")
    entries = list(glob.glob(pattern, recursive=True))
    return [entry for entry in entries if os.path.isfile(entry)]


def decrypt_file(secret_key, file_path):
    with open(file_path, "rb") as infile:
        iv = infile.read(16)
        ciphertext = infile.read()

    cipher = AES.new(secret_key, AES.MODE_CBC, bytes(iv))
    plaintext = cipher.decrypt(pad(ciphertext, 16))

    with open(file_path, "wb") as outfile:
        outfile.write(plaintext)


def decrypt_dir(secret_key, dir_path):
    file_paths = list_files(dir_path)
    for file_path in file_paths:
        decrypt_file(secret_key, file_path)
        file_ext = os.path.splitext(file_path)[1]
        if file_ext in [".xhtml", ".opf", ".ncx"]:
            clean_xml(file_path)


def get_title(soup):
    return soup.title.text.strip()


def unpack_epub(epub_path):
    basename = os.path.splitext(epub_path)[0]
    unpack_dir = os.path.abspath(f"{basename}.tmp")

    if not os.path.exists(unpack_dir):
        os.makedirs(unpack_dir)

    with zipfile.ZipFile(epub_path, "r") as zf:
        zf.extractall(unpack_dir)
    return unpack_dir


def zip_dir(zip_object, base_path, dir_path):
    file_paths = list_files(dir_path)
    for file_path in file_paths:
        dest_path = os.path.relpath(file_path, base_path)
        zip_object.write(file_path, dest_path)


def pack_epub(decrypted_dir):
    soup = parse_metadata(decrypted_dir)
    title = get_title(soup)
    parent_directory = os.path.abspath(os.path.join(decrypted_dir, os.pardir))
    zip_path = os.path.join(parent_directory, f"{title}.epub")

    mime_path = os.path.join(decrypted_dir, "mimetype")
    meta_path = os.path.join(decrypted_dir, "META-INF")
    oebps_path = os.path.join(decrypted_dir, "OEBPS")

    rmf(zip_path)

    with zipfile.ZipFile(zip_path, "a") as zipf:
        zipf.write(mime_path, "mimetype")
        zip_dir(zipf, decrypted_dir, meta_path)
        zip_dir(zipf, decrypted_dir, oebps_path)

    return parent_directory


def clean_xml(xml_path):
    with open(xml_path, errors="ignore", encoding="utf-8") as rf:
        content = rf.read()
    soup = BeautifulSoup(content, features="xml")
    with open(xml_path, "w", errors="ignore", encoding="utf-8") as wf:
        content = wf.write(soup.prettify())


def decypt_epub(epub_path, dat_path):
    epub_path = os.path.abspath(epub_path)
    dat_path = os.path.abspath(dat_path)

    secret_key = get_key(device_id, dat_path)
    unpack_dir = unpack_epub(epub_path)
    decrypt_dir(secret_key, unpack_dir)
    dest_dir = pack_epub(unpack_dir)
    rmtree(unpack_dir)

    return dest_dir


def load_settings():
    global usercode, device_id, settings

    try:
        with open("settings.json") as rf:
            settings = json.load(rf)
    except:
        settings = {}

    if not settings.get("usercode", None):
        settings["usercode"] = get_usercode()

    with open("settings.json", "w") as wf:
        json.dump(settings, wf)

    if not settings.get("device_id", None):
        settings["device_id"] = get_device_id()

    with open("settings.json", "w") as wf:
        json.dump(settings, wf)

    usercode = settings["usercode"]
    device_id = settings["device_id"]


def usage():
    exec_path = sys.argv[0]
    print("Usage:")
    print(f"    {exec_path} [path_to_book_directory]")
    print(f"Book directories are under {LIBRARY_PATH}")


# unused for now
def parse_settings():
    user_code = 8267222
    with open(Rf"{APPDATA}\Ridibooks\datastores\global\Settings", "rb") as rf:
        ciphertext = rf.read()
    key = hashlib.sha1(f"Settings-{user_code}".encode()).hexdigest()[2:18]
    cipher = AES.new(key.encode(), AES.MODE_ECB)
    plaintext = cipher.decrypt(ciphertext[256:])
    return plaintext


# unused for now
def list_books():
    with open(Rf"{APPDATA}\Ridibooks\datastores\user\_{usercode}\DownloadBookAll", "rb") as rf:
        ciphertext = rf.read()
    key = hashlib.sha1(f"DownloadBookAll-{usercode}".encode()).hexdigest()[2:18]
    cipher = AES.new(key.encode(), AES.MODE_ECB)
    plaintext = cipher.decrypt(ciphertext[256:])
    # plaintext = unpad(plaintext, 16)
    return json.loads(plaintext)


def main():
    load_settings()

    args = sys.argv
    if len(args) != 2:
        usage()
        quit()

    book_dir = args[1]
    book_code = os.path.basename(os.path.normpath(book_dir))
    epub_path = glob.glob(Rf"{book_dir}\{book_code}*.epub")[0]
    dat_path = glob.glob(Rf"{book_dir}\{book_code}*.dat")[0]
    dest_dir = decypt_epub(epub_path, dat_path)

    print(f"Decrypted epub can be found at {dest_dir}")


if __name__ == "__main__":
    main()
