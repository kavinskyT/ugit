import hashlib
import os

GIT_DIR = '.ugit'

def init():
    os.makedirs(GIT_DIR)
    os.makedirs(os.path.join(GIT_DIR, 'objects'))
    
def hash_object(data):
    oid = hashlib.sha1(data).hexdigest()
    with open(os.path.join(GIT_DIR, 'objects', oid), 'wb') as out:
        out.write(data)
    return oid

def get_object(oid):
    with open(os.path.join(GIT_DIR, 'objects', oid), 'rb') as f:
        return f.read()