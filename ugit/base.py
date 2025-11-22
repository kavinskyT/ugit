# This module will have the basic higher-level logic of ugit.

import itertools
import operator
import os
import string

from collections import deque, namedtuple

from . import data
from . import diff


def init():
    data.init()
    data.update_ref('HEAD', data.RefValue(symbolic=True, value='refs/heads/master'))


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
            result.update(get_tree(oid, f'{path}/'))
        else:
            assert False, f'Unknown tree entry {type_}'
    return result


# This function wals over all files in the working directory, 
# put them in the object database and create a dict that holds 
# all the OIDs. This dictionary will represent a "tree" without
# actually writitng a tree object.
def get_working_tree():
    result = {}
    for root, _, filenames in os.walk('.'):
        for filename in filenames:
            path = os.path.relpath(f'{root}/{filename}') # start_value is os.curdir by default, which is always .
            if is_ignored(path) or not os.path.isfile(path):   
                continue
            with open(path, 'rb') as f:
                result[path] = data.hash_object(f.read())
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
            
            
# This function takes two tree + first common ancestor and extract a merged version of them into the working 
# directory. It does so by calling diff.merge_trees() and writing the resulting merged
# tree to the working directory.
def read_tree_merged(t_base, t_HEAD, t_other):
    _empty_current_directory()
    for path, blob in diff.merge_trees(
            get_tree(t_base), get_tree(t_HEAD), get_tree(t_other)).items():
        os.makedirs(f'./{os.path.dirname(path)}', exist_ok=True)
        with open(path, 'wb') as f:
            f.write(blob)
            

# This function creates an enriched tree. It makes HEAD to point to this commit
def commit(message):
    commit = f'tree {write_tree()}\n'
    
    HEAD = data.get_ref('HEAD').value
    if HEAD:
        commit += f'parent {HEAD}\n'
    MERGE_HEAD = data.get_ref('MERGE_HEAD').value
    if MERGE_HEAD:
        commit += f'parent {MERGE_HEAD}\n'
        data.delete_ref('MERGE_HEAD', deref=False)
    
    commit += '\n'
    commit += f'{message}\n'
    
    oid = data.hash_object(commit.encode(), 'commit')
    
    # Update the HEAD. HEAD is normally a symbolic link: 
    # it points to another ref that actually points to an oid.
    data.update_ref('HEAD', data.RefValue(symbolic=False, value=oid))
    # Explanation of how commit modifies the pointing of current branch and updates 
    # HEAD: by calling update_ref on HEAD with new value, the recursive function
    # _get_internal_ref() is called. In this way, the updating happens with 
    # respect to the ref (current branch) that is pointed by HEAD (which is a 
    # symbolic link so we dive into a recursive step). HEAD isn't really updated 
    # since it keeps pointing to the ref that represents the branch.
    
    return oid


# This functions sets the project to a desired commit. 
# The HEAD is updated accordingly to point to the retrieved commit. 
def checkout(name):
    oid = get_oid(name)
    commit = get_commit(oid)
    read_tree(commit.tree)
    
    # We can either checkout a commit by its OID or ref. However, 
    # by checking out an OID, HEAD point to that OID but does not point 
    # to the branch ref anymore. This means we are in a detached HEAD state.
    if is_branch(name):
        HEAD = data.RefValue(symbolic=True, value=f'refs/heads/{name}')
    else:
        HEAD = data.RefValue(symbolic=False, value=oid)

    data.update_ref ('HEAD', HEAD, deref=False) 
    

# Reset is similar to checkout but it moves the branch reference too 
# (no detached head state). By default, the content of the directory is not 
# changed accordingly to the default commit. In Git, to do so you would use 
# git reset --hard <hash>. The default behaviour serves the purpose to rewrite 
# commit hisotry while preserving your work changes.
def reset(oid):
    data.update_ref('HEAD', data.RefValue(symbolic=False, value=oid))
    

def get_merge_base(oid1, oids2):
    parents1= set(iter_commits_and_parents({oid1}))
    
    for oid in iter_commits_and_parents({oids2}):
        if oid in parents1:
            return oid

def create_tag(name, oid):
    data.update_ref(f'refs/tags/{name}', data.RefValue(symbolic=False, value=oid))
    
    
# This function takes the tree of the HEAD and the tree of the other branch 
# we want to merge with and calls read_tree_merged()
def merge(other):
    HEAD = data.get_ref('HEAD').value
    assert HEAD
    merge_base = get_merge_base(other, HEAD)
    c_other = get_commit(other)
    
    # Handle fast-forward merge (when common base is equal to HEAD)
    if merge_base == HEAD:
        read_tree(c_other.tree)
        data.update_ref('HEAD',
                        data.RefValue(symbolic=False, value=other))
        print('Fast-forward merge, no need to commit')
        return

    # The presence of a ref 'MERGE_HEAD' is needed so that it is known that 
    # the next commit is a merge commit with two parents.
    data.update_ref('MERGE_HEAD', data.RefValue(symbolic=False, value=other))
    
    c_base = get_commit(merge_base)
    c_HEAD = get_commit(HEAD)
    read_tree_merged(c_base.tree, c_HEAD.tree, c_other.tree)
    print('Merged in working tree\nPlease commit')


def create_branch(name, oid):
    data.update_ref(f'refs/heads/{name}', data.RefValue(symbolic=False, value=oid))
    

def iter_branch_names():
    for refname, _ in data.iter_refs('refs/heads/'):
        yield os.path.relpath(refname, 'refs/heads/')


def is_branch(branch):
    return data.get_ref(f'refs/heads/{branch}').value is not None


def get_branch_name():
    HEAD = data.get_ref('HEAD', deref=False)
    if not HEAD.symbolic: # DETACHED HEAD
        return None
    HEAD = HEAD.value
    assert HEAD.startswith('refs/heads/')
    return os.path.relpath(HEAD, 'refs/heads/')


Commit = namedtuple('Commit', ['tree', 'parents', 'message'])


# Given an oid it returns the associated Commit tuple
def get_commit(oid):
    parents = []
    
    commit = data.get_object(oid, 'commit').decode()
    lines = iter(commit.splitlines())
    # takewhile iters on iterable as long as the predicate is true. In this case the
    # predicate is operator.truth, which checks if the object is true.
    for line in itertools.takewhile(operator.truth, lines):
        key, value = line.split (' ', 1)
        if key == 'tree':
            tree = value
        elif key == 'parent':
            parents.append(value)
        else: 
            assert False, f'Unknown field {key}'
        
    message = '\n'.join(lines)
    return Commit(tree=tree, parent=parents, message=message)


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
        # Return first parent next
        oids.extendleft(commit.parents[:1])
        # Return other parents later (first we want to run all the way to the root)
        oids.extend(commit.parents[1:])


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
        if data.get_ref(ref, deref=False).value:
            return data.get_ref(ref).value
        
    # Name is SHA1 (SHA 1 hash is 160 bits = 40 hex digits)
    is_hex = all(c in string.hexdigits for c in name)
    if len(name) == 40 and is_hex:
        return name
    
    assert False, f'Unknown name {name}'
    
    
def is_ignored(path):
    return '.ugit' in path.split('/')