# This module contains all the remote synchronization code

import os

from . import base
from . import data


REMOTE_REFS_BASE = 'refs/heads/'
LOCAL_REFS_BASE = 'refs/remote/'


def fetch(remote_path):
    # Gets refs from server
    refs = _get_remote_refs(remote_path, REMOTE_REFS_BASE)
    
    # Fetch missing objects by iterating on commits and fetching objects on demand
    for oid in base.iter_objects_in_commits(refs.values()):
        # Objects that misses are either new files of modified versions of an 
        # existing file.
        data.fetch_object_if_missing(oid, remote_path)
    
    # Update local refs to match server
    for remote_name, value in refs.items():
        refname = os.path.relpath(remote_name, REMOTE_REFS_BASE)
        data.update_ref(f'{LOCAL_REFS_BASE}/{refname}',
                        data.RefValue(symbolic=False, value=value))
        

def push(remote_path, refname):
    # Gets refs data
    local_ref = data.get_ref(refname).value
    assert local_ref
    
    objects_to_push = base.iter_objects_in_commits({local_ref})
    
    # Push all objects
    for oid in objects_to_push:
        data.push_object(oid, remote_path)
        
    # Update server ref to our value
    with data.change_git_dir(remote_path):
        data.update_ref(refname, data.RefValue(symbolic=False, value=local_ref))
            

def _get_remote_refs(remote_path, prefix=''):
    with data.change_git_dir(remote_path):
        return {refname: ref.value for refname, ref in data.iter_refs(prefix)}