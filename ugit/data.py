# This module manages the data in .ugit directory. Here will
# be the code that actually touches files on disk.

import hashlib
import os

GIT_DIR = '.ugit'

def init():
    os.makedirs(GIT_DIR)
    os.makedirs(os.path.join(GIT_DIR, 'objects'))
    
# Set the ref name for an object    
def update_ref(ref, oid):
    ref_path = os.path.join(GIT_DIR, ref)
    os.makedirs(os.path.dirname(ref_path), exist_ok=True)
    with open(ref_path, 'w') as f:
        f.write(oid)
        

# Get the ref name for an object
def get_ref(ref):
    ref_path = os.path.join(GIT_DIR, ref)
    if os.path.isfile(ref_path):
        with open(ref_path) as f:
            return f.read().strip()
        
        
# In the caller, data is encoded into bytes.    
def hash_object(data, type_='blob'):
    obj = type_.encode() + b'\x00' + data
    oid = hashlib.sha1(obj).hexdigest()
    with open(os.path.join(GIT_DIR, 'objects', oid), 'wb') as out:
        out.write(obj)
    return oid


# It return the content encoded into bytes so, when this function is called,
# the result is usually decoded.
def get_object(oid, expected='blob'):
    with open(os.path.join(GIT_DIR, 'objects', oid), 'rb') as f:
        obj = f.read()
    
    type_, _, content = obj.partition(b'\x00')
    type_ = type_.decode()
    
    if expected is not None:
        assert type_ == expected, f'Expected {expected}, got {type_}'
    return content