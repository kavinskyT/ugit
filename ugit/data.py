# This module manages the data in .ugit directory. Here will
# be the code that actually touches files on disk.

import hashlib
import os

from collections import namedtuple

GIT_DIR = '.ugit'

def init():
    os.makedirs(GIT_DIR)
    os.makedirs(os.path.join(GIT_DIR, 'objects'))
    
    
# This represents the value of a ref, whether it's an actual ref (pointing to oid) 
# or a symbolic one (pointing to another ref)
RefValue = namedtuple('RefValue', ['symbolic', 'value'])    
    
    
# Set the ref name for an object (the object can either be an oid or another ref)
def update_ref(ref, value, deref=True):
    ref = _get_ref_internal(ref, deref)[0]
    
    assert value.value
    if value.symbolic:
        value = f'ref:{value.value}'
    else:
        value = value.value
    
    ref_path = os.path.join(GIT_DIR, ref)
    os.makedirs(os.path.dirname(ref_path), exist_ok=True)
    with open(ref_path, 'w') as f:
        f.write(value)
        

# Get the ref name for an object
def get_ref(ref, deref=True):
    return _get_ref_internal(ref, deref)[1]


# This function is needed to resolve a ref. If a ref is symbolic, the function 
# retrieves the last ref in the chain that actually refers to an oid (commit)
def _get_ref_internal(ref, deref):
    ref_path = os.path.join(GIT_DIR, ref)
    value = None
    
    if os.path.isfile(ref_path):
        with open(ref_path) as f:
            value = f.read().strip()

    symbolic = bool(value) and value.startswith('ref:')
    if symbolic:
        value = value.split(':', 1)[1].strip()
        if deref:
            return _get_ref_internal(value, deref=True)
    
    return ref, RefValue(symbolic=symbolic, vlaue=value) 
        
        
def iter_refs(deref=True):
    refs = ['HEAD']
    # This is needed to get all the refs in the path format expected by get_ref, 
    # which appends ref to GIT_DIR
    for root, _, filenames in os.walk(os.path.join(GIT_DIR, 'refs')):
        root = os.path.relpath(root, GIT_DIR)
        refs.extend(os.path.join(root, name) for name in filenames)
        
    for refname in refs:
        yield refname, get_ref(refname, deref=deref)
        
        
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