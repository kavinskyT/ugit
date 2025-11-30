# This module manages the data in .ugit directory. Here will
# be the code that actually touches files on disk.

import hashlib
import os
import shutil

from collections import namedtuple
from contextlib import contextmanager

# Will be initialized in cli.main()
GIT_DIR = None


# We need to temporarily look inside other repositories (e.g., during fetch/push),
# which means ugit must be able to switch its GIT_DIR on the fly.
#
# The @contextmanager decorator lets us write this as a "with" block:
#
#     with change_git_dir('some/repo'):
#         ... operate on that repo ...
#
# This temporarily replaces the global GIT_DIR and *automatically restores*
# the previous value after the block finishes, even if an error occurs.
#
# This mirrors how real Git internally swaps its .git directory when dealing
# with remotes. It also keeps our code safe and easy to reason about while
# we learn how repository synchronization works.
#
# In short:
#   - Enter block  → point GIT_DIR to new_repo/.ugit
#   - Exit block   → restore original GIT_DIR
#
# This feature is essential for implementing commands like fetch and push.
@contextmanager
def change_git_dir(new_dir):
    global GIT_DIR
    old_dir = GIT_DIR
    GIT_DIR = f'{new_dir}/.ugit'
    yield
    GIT_DIR = old_dir

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


# It removes an existing ref
def delete_ref(ref, deref=True):
    ref = _get_ref_internal(ref, deref)[0]
    os.remove(f'{GIT_DIR}/{ref}')


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
    
    return ref, RefValue(symbolic=symbolic, value=value) 
        
        
def iter_refs(prefix='', deref=True):
    refs = ['HEAD', 'MERGE_HEAD']
    # This is needed to get all the refs in the path format expected by get_ref, 
    # which appends ref to GIT_DIR
    for root, _, filenames in os.walk(os.path.join(GIT_DIR, 'refs')):
        root = os.path.relpath(root, GIT_DIR)
        refs.extend(os.path.join(root, name) for name in filenames)
        
    for refname in refs:
        if not refname.startswith(prefix):
            continue
        ref = get_ref(refname, deref=deref)
        if ref.value: # To check existence of MERGE_HEAD
            yield refname, ref
        
        
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


def object_exists(oid):
    return os.path.isfile(f'{GIT_DIR}/objects/{oid}')


def fetch_object_if_missing(oid, remote_git_dir):
    if object_exists(oid):
        return
    remote_git_dir += '/.ugit'
    shutil.copy(f'{remote_git_dir}/objects/{oid}',
                f'{GIT_DIR}/objects/{oid}')
    
    
# Copies a local object to a remote repo
def push_object(oid, remote_git_dir):
    remote_git_dir += '/.ugit'
    shutil.copy(f'{GIT_DIR}/objects/{oid}',
                f'{remote_git_dir}/objects/{oid}')