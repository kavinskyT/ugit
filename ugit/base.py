# This module will have the basic higher-level logic of ugit.

import itertools
import operator
import os
import string

from collections import deque, namedtuple

from . import data

# This function saves a tree as an object. If there are subfolders, the process 
# is done recursively and the OID of a folder is saved in the tree object 
# corresponding to the super folder.
def write_tree(directory='.'):
    entries = []
    with os.scandir(directory) as it:
        for entry in it:
            full = os.path.join(directory, entry.name)
            if is_ignored(full):
                continue
            if entry.is_file(follow_symlinks=False):
                type_ = 'blob'
                with open(full, 'rb') as f:
                    oid = data.hash_object(f.read())
            elif entry.is_dir(follow_symlinks=False):
                type_ = 'tree'
                oid = write_tree(full)
            entries.append((entry.name, oid, type_))
                
    tree = ''.join(f'{type_} {oid} {name}\n'
                   for name, oid, type_
                   in sorted(entries))
    return data.hash_object(tree.encode(), 'tree')

# It generates, line by line, the content of a tree.
def _iter_tree_entries(oid):
    if not oid:
        return
    tree = data.get_object(oid, 'tree')
    for entry in tree.decode().splitlines():
        type_, oid, name = entry.split(' ', 2)
        yield type_, oid, name
        
# It recursively parse a tree into a dictionary.
def get_tree(oid, base_path=''):
    result = {}
    for type_, oid, name in _iter_tree_entries(oid):
        assert '/' not in name
        assert name not in ('..', '.')
        path = os.path.join(base_path, name)
        if type_ == 'blob':
            result[path] = oid
        elif type_ == 'tree':
            result.update(get_tree(oid, 'f{path}/'))
        else:
            assert False, f'Unknown tree entry {type_}'
    return result


# It deletes all the content of the folder.
def _empty_current_directory():
    for root, dirnames, filenames in os.walk('.', topdown=False):
        for filename in filenames:
            path = os.path.relpath(os.path.join(root, filename))
            if is_ignored(path) or not os.path.isfile(path):
                continue
            os.remove(path)
        for dirname in dirnames:
            path = os.path.relpath(os.path.join(root, dirname))
            if is_ignored(path):
                continue
            try:
                os.rmdir(path)
            except (FileNotFoundError, OSError):
                # Deletion might fail if the directory contains ignored files,
                # so it's OK
                pass


# This function rebuild the directory as saved in the corresponding tree.
def read_tree(tree_oid):
    _empty_current_directory()
    for path, oid in get_tree(tree_oid, base_path='./').items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data.get_object(oid))
            

# This function creates an enriched tree. It makes HEAD to point to this commit
def commit(message):
    commit = f'tree {write_tree()}\n'
    
    HEAD = data.get_ref('HEAD')
    if HEAD:
        commit += f'parent {HEAD}\n'
    
    commit += '\n'
    commit += f'{message}\n'
    
    oid = data.hash_object(commit.encode(), 'commit')
    
    # Update the HEAD
    data.update_ref('HEAD', oid)
    
    return oid


def create_tag(name, oid):
    data.update_ref(f'refs/tags/{name}', oid)
    

def create_branch(name, oid):
    data.update_ref(f'refs/heads/{name}', oid)


Commit = namedtuple('Commit', ['tree', 'parent', 'message'])


# Given an oid it returns the associated Commit tuple
def get_commit(oid):
    parent = None
    
    commit = data.get_object(oid, 'commit').decode()
    lines = iter(commit.splitlines())
    # takewhile iters on iterable as long as the predicate is true. In this case the
    # predicate is operator.truth, which checks if the object is true.
    for line in itertools.takewhile(operator.truth, lines):
        key, value = line.split (' ', 1)
        if key == 'tree':
            tree = value
        elif key == 'parent':
            parent = value
        else: 
            assert False, f'Unknown field {key}'
        
    message = '\n'.join(lines)
    return Commit(tree=tree, parent=parent, message=message)


def iter_commits_and_parents(oids):
    # A deque is a double-endend queue. You can pop and append either from both ends.
    oids = deque(oids)
    visited = set()
    
    # oids contains refs so when we pop a ref we append its parent so the next 
    # iteration we pop the parent and so on until the root.
    while oids:
        oid = oids.popleft()
        if not oid or oid in visited:
            continue
        visited.add(oid)
        yield oid
        
        commit = get_commit(oid)
        # Return parent next
        oids.appendleft(commit.parent)


def get_oid(name):
    if name == '@': name = 'HEAD'
    
    # Name is ref
    refs_to_try = [
        f'{name}',
        os.path.join('refs', name),
        os.path.join('refs', 'tags', name),
        os.path.join('refs', 'heads', name)
    ]
    
    for ref in refs_to_try:
        if data.get_ref(ref):
            return data.get_ref(ref)
        
    # Name is SHA1 (SHA 1 hash is 160 bits = 40 hex digits)
    is_hex = all(c in string.hexdigits for c in name)
    if len(name) == 40 and is_hex:
        return name
    
    assert False, f'Unknown name {name}'
    
    
def is_ignored(path):
    return '.ugit' in path.split('/')


# This functions sets the project to a desired commit. 
# The HEAD is updated accordingly to point to the retrieved commit. 
def checkout(oid):
    commit = get_commit(oid)
    read_tree(commit.tree)
    data.update_ref('HEAD', oid)