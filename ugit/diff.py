# This module will contain the code that deals with 
# computing differences between objects

from collections import defaultdict

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
    output = ''
    for path, o_from, o_to in compare_trees(t_from, t_to):
        if o_from != o_to:
            output += f'changed: {path}\n'
    return output