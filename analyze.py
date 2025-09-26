import tarfile
import hashlib
from pathlib import Path

total_size = 0
total_tars = 0

change_entries = 0
wh_entries = 0

testbed_size = 0
conda_size = 0
other_size = 0

conda_hashes = {}
testbed_hashes = {}

def hash(tf: tarfile.TarFile, member: tarfile.TarInfo):
    f = tf.extractfile(member)
    h = hashlib.sha256()
    for chunk in iter(lambda: f.read(8192), b""):
        h.update(chunk)
    f.close()
    return h.hexdigest()

for path in Path('./layout/blobs/sha256').iterdir():
    print(path)
    try:
        with tarfile.open(path, "r") as tf:
            total_tars += 1
            for member in tf.getmembers():
                if Path(member.name).name.startswith('.wh'):
                    wh_entries += 1
                else:
                    change_entries += 1
                    
                if member.name.startswith('opt/miniconda3/'):
                    conda_size += member.size
                    if member.isfile(): 
                        conda_hashes[hash(tf, member)] = member.size
                    
                elif member.name.startswith('testbed/'):
                    testbed_size += member.size
                    
                    if member.isfile(): 
                        testbed_hashes[hash(tf, member)] = member.size
                else:
                    other_size += member.size
                    
                total_size += member.size
    except tarfile.ReadError:
        # JSON blob
        pass
    
print(f"Total number of layers: {total_tars}")
print(f"Total raw layer sizes: {total_size}")
print(f"Total number of files: {change_entries}")
print(f"Total number of deletions: {wh_entries}")
print(f"Conda size: {conda_size/1024/1024/1024:.2f} GiB (unique: {sum(conda_hashes.values())/1024/1024/1024:.2f} GiB)")
print(f"Testbed size: {testbed_size/1024/1024/1024:.2f} GiB (unique: {sum(testbed_hashes.values())/1024/1024/1024:.2f} GiB)")
print(f"Other files: {other_size/1024/1024/1024:.2f} GiB")