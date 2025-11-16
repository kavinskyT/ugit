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
            output, _ = proc.communicate()
        
        return output