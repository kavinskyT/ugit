# This module is in charge of parsing and processing
# user input.

import argparse
import os
import subprocess
import sys
import textwrap

from . import base
from . import data
from . import diff

def main():
    args = parse_args()
    args.func(args)


def parse_args():
    parser = argparse.ArgumentParser()

    commands = parser.add_subparsers(dest='command')
    commands.required = True
    
    # We assign the function to the variable oid. We use the variable to set an expected 
    # type of certain functions' arguments. In general, this can be done using a 
    # type or a function.
    oid = base.get_oid

    init_parser = commands.add_parser('init')
    init_parser.set_defaults(func=init)
    
    hash_object_parser = commands.add_parser('hash-object')
    hash_object_parser.set_defaults(func=hash_object)
    hash_object_parser.add_argument('file')
    
    cat_file_parser = commands.add_parser('cat-file')
    cat_file_parser.set_defaults(func=cat_file)
    cat_file_parser.add_argument('object', type=oid)
    
    write_tree_parser = commands.add_parser('write-tree')
    write_tree_parser.set_defaults(func=write_tree)

    read_tree_parser = commands.add_parser('read-tree')
    read_tree_parser.set_defaults(func=read_tree)
    read_tree_parser.add_argument('tree', type=oid)
    
    commit_parser = commands.add_parser('commit')
    commit_parser.set_defaults(func=commit)
    commit_parser.add_argument('-m', '--message', required=True)
    
    log_parser = commands.add_parser('log')
    log_parser.set_defaults(func=log)
    log_parser.add_argument('oid', default='@', type=oid, nargs='?')
    
    show_parser = commands.add_parser('show')
    show_parser.set_defaults(func=show)
    show_parser.add_argument('oid', default='@', type=oid, nargs='?')
    
    diff_parser = commands.add_parser('diff')
    diff_parser.set_defaults(func=_diff)
    diff_parser.add_argument('commit', default='@', type=oid, nargs='?')
    
    checkout_parser = commands.add_parser('checkout')
    checkout_parser.set_defaults(func=checkout)
    checkout_parser.add_argument('commit')
    
    tag_parser = commands.add_parser('tag')
    tag_parser.set_defaults(func=tag)
    tag_parser.add_argument('name')
    tag_parser.add_argument('oid', default='@', type=oid, nargs='?')
    
    branch_parser = commands.add_parser('branch')
    branch_parser.set_defaults(func=branch)
    branch_parser.add_argument('name', nargs='?')
    branch_parser.add_argument('start_point', default='@', type=oid, nargs='?')
    
    k_parser = commands.add_parser('k')
    k_parser.set_defaults(func=k)    
    
    status_parser = commands.add_parser('status')
    status_parser.set_defaults(func=status)
    
    reset_parser = commands.add_parser('reset')
    reset_parser.set_defaults(func=reset)
    reset_parser.add_argument('commit', type=oid)
    
    merge_parser = commands.add_parser('merge')
    merge_parser.set_defaults(func=merge)
    merge_parser.add_argument('commit', type=oid)
    
    return parser.parse_args()


def init(args):
    base.init()
    print (f'Initialized empty ugit repository in {os.path.join(os.getcwd(), data.GIT_DIR)}')
    

def hash_object(args):
    with open(args.file, 'rb') as f:
        print(data.hash_object(f.read()))
        

def cat_file(args):
    sys.stdout.flush()
    sys.stdout.buffer.write(data.get_object(args.object, expected=None))
    

def write_tree(args):
    print(base.write_tree())
    
    
def read_tree(args):
    base.read_tree(args.tree)
    
    
def commit(args):
    print(base.commit(args.message))
    

def _print_commit(oid, commit, refs=None):
    refs_str = f'({", ".join(refs)})' if refs else ''
    print(f'commit {oid}{refs_str}')
    print(textwrap.indent(commit.message, '     '))
    print('')
    

def log(args):
    refs = {}
    for refname, ref in data.iter_refs():
        refs.setdefault(ref.value, []).append(refname)
    
    for oid in base.iter_commits_and_parents({args.oid}):
        commit = base.get_commit(oid)
        _print_commit(oid, commit, refs.get(oid))
        
        
def show(args):
    if not args.oid:
        return
    commit = base.get_commit(args.oid)
    parent_tree = None
    if commit.parent:
        parent_tree = base.get_commit(commit.parent).tree
        
    _print_commit(args.oid, commit)
    result = diff.diff_trees(
        base.get_tree(parent_tree), base.get_tree(commit.tree))
    sys.stdout.flush()
    sys.stdout.buffer.write(result)
        

def _diff(args):
    tree = args.commit and base.get_commit(args.commit).tree # var = var1 and var2 in Python uses the logical and operator, which evaluates to the first falsy value if one exists, otherwise it returns the last value.
    
    result = diff.diff_trees(base.get_tree(tree), base.get_working_tree())
    sys.stdout.flush()
    sys.stdout.buffer.write(result)


def checkout(args):
    base.checkout(args.commit)
    

def tag(args):
    base.create_tag(args.name, args.oid)
    
    
# If no name is provided the function lists all the branches. 
# Otherwise it creates the specified branch.
def branch(args):
    if not args.name:
        current = base.get_branch_name()
        for branch in base.iter_branch_names():
            prefix = '*' if branch == current else ' '
            print(f'{prefix} {branch}')
    else:
        base.create_branch (args.name, args.start_point)
        print (f'Branch {args.name} created at {args.start_point[:10]}')
    
    
def k(args):
    dot = 'digraph commits {\n'
    
    oids = set()
    for refname, ref in data.iter_refs(deref=False):
        dot += f'"{refname}" [shape=note]\n'
        dot += f'"{refname}" -> "{ref.value}"\n' 
        if not ref.symbolic:
            oids.add(ref.value)
        
    for oid in base.iter_commits_and_parents(oids):
        commit = base.get_commit(oid)
        dot += f'"{oid}" [shape=box style=filled label="{oid[:10]}"]\n'
        if commit.parent:
            dot += f'"{oid}" -> "{commit.parent}"\n'
            
    dot += '}'
    print(dot)
    
    with subprocess.Popen(
        ['dot', '-Tx11', '/dev/stdin'],
        stdin=subprocess.PIPE) as proc:
        proc.communicate(dot.encode())
        

def status(args):
    HEAD = base.get_oid('@')
    branch = base.get_branch_name()
    if branch:
        print(f'On branch {branch}')
    else:
        print(f'HEAD detached at {HEAD[:10]}')
        
    print('\nChanges to be committed:\n')
    HEAD_tree = HEAD and base.get_commit(HEAD).tree
    for path, action in diff.iter_changed_files(base.get_tree(HEAD_tree),
                                                base.get_working_tree()):
        print(f'{action:>12}: {path}')
        

def reset(args):
    base.reset(args.commit)
    
    
# Assuming that both HEAD and some-branch have a file named main.py in 
# their tree, when merging, we want to create a new main.py that will 
# contain the content of both HEAD's main.py and some-branch's main.py.    
def merge(args):
    base.merge(args.commit)