import json
import tarfile
import subprocess

from pathlib import Path

LAYOUT = Path("./layout")

index = json.load(open(str(LAYOUT / 'index.json')))

config_blobs = []
manifest_blobs = []
layer_blobs = []

for x in index['manifests']:
    manifest_blobs.append(x['digest'].split(":")[1])
    
for m in manifest_blobs:
    with open(LAYOUT / 'blobs'/ 'sha256' / m) as fp:
        parsed = json.load(fp)

        config_blobs.append(parsed['config']['digest'].split(":")[1])
        layers_blobs = [x['digest'].split(":")[1] for x in parsed['layers']]
        layer_blobs.append(layers_blobs)

with tarfile.open("out/layout.tar", "w") as tar:
    seen = set()
    for blobs in sorted(layer_blobs, key=lambda x: len(x), reverse=True):
        for blob in blobs:
            if blob not in seen:
                print(f'Adding {blob}')
                tar.add(LAYOUT / 'blobs' / 'sha256' / blob)
                seen.add(blob)
                
    for blob in manifest_blobs + config_blobs:
        tar.add(LAYOUT / 'blobs' / 'sha256' / blob)

    tar.add(LAYOUT / 'index.json')
    tar.add(LAYOUT / 'oci-layout')

subprocess.run(["zstd", "-f", "-T100", "-19", "--long=31", "out/layout.tar", "-o", "out/layout.tar.zst"])