# This module will contain the code that deals with 
# computing differences between objects

import subprocess

from collections import defaultdict
from tempfile import NamedTemporaryFile as Temp

from . import data

# This function takes a list of trees and will return them grouped by filename. 
# For each file we have its OIDs in the different trees.
def compare_trees(*trees): # A parameter prefixed with a single * is used to collect an arbitrary number of positional arguments into a tuple
    # defaultdict automatically assigns a deafult valut to keys that 
    # do not exists. In this scenario, the default value is an 
    # array of None with length equal to the length of the parameter tuple.
    entries = defaultdict(lambda: [None] * len(trees))
    # iteration on trees
    for i, tree in enumerate(trees):
        # within tree, iteration on couple file (path) and correspondent oid
        for path, oid in tree.items():
            entries[path][i] = oid
            
    for path, oids in entries.items():
        yield (path, *oids)
        

# This function takes two trees and output alla changed 
# paths along with the change type (deleted, created, modified).
def iter_changed_files(t_from, t_to):
    for path, o_from, o_to in compare_trees(t_from, t_to):
        if o_from != o_to:
            action = ('new file' if not o_from else
                      'deleted' if not o_to else
                      'modified')
            yield path, action
        

# This function takes two tree, compares them and 
# return all entries that have different OIDs.
def diff_trees(t_from, t_to):
    output = b'' # because it will be a byte string 
    for path, o_from, o_to in compare_trees(t_from, t_to):
        if o_from != o_to:
            output += diff_blobs(o_from, o_to, path)
    return output


def diff_blobs(o_from, o_to, path='blob'):
    with Temp() as f_from, Temp() as f_to:
        for oid, f in ((o_from, f_from), (o_to, f_to)):
            if oid:
                f.write(data.get_object(oid))
                f.flush()
                
        with subprocess.Popen(
            ['diff', '--unified', '--show-c-function',
             '--label', f'a/{path}', f_from.name,
             '--label', f'b/{path}', f_to.name],
            stdout=subprocess.PIPE) as proc:
            # proc.communicate() returns a tuple (stdout_bytes, stderr_bytes)
            output, _ = proc.communicate()
        
        return output
    

# This function gets two tree and in turn calls merge_blobs() 
# to merge each two files in the trees, outputting one merged tree.
def merge_trees(t_base, t_HEAD, t_other):
    tree = {}
    for path, o_base, o_HEAD, o_other in compare_trees(t_base, t_HEAD, t_other):
        tree[path] = data.hash_object (merge_blobs (o_base, o_HEAD, o_other))
    return tree    


# This function gets two OIDs and returns their merged content.
def merge_blobs(o_base, o_HEAD, o_other):
    with Temp() as f_base, Temp() as f_HEAD, Temp() as f_other:
        
        # Write blobs to files
        for oid, f in ((o_base, f_base), (o_HEAD, f_HEAD), (o_other, f_other)):
            if oid:
                # The temporary files serve the purpose of holding OID-corresponding content.
                f.write(data.get_object(oid))
                f.flush()
                
        with subprocess.Popen(
            ['diff3', '-m',
             '-L', 'HEAD', f_HEAD.name,
             '-L', 'BASE', f_base.name,
             '-L', 'MERGE_HEAD', f_other.name,
             ], stdout=subprocess.PIPE) as proc:
            output, _ = proc.communicate()
            assert proc.returncode in (0, 1)
            
        return output