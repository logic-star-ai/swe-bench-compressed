import json
import os
import sys
import time
import uuid
import asyncio
import datasets
import subprocess

from pathlib import Path
from tqdm import tqdm

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

NAMESPACE = 'logicstar'
LAYOUT = 'layout'

target_sem = asyncio.Semaphore(1)

verified = datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
instances_by_repo = defaultdict(list)

for instance in verified:
    repo, name = instance["instance_id"].split("__")
    instances_by_repo[repo].append(
        (
            instance["instance_id"],
            f"docker.io/swebench/sweb.eval.x86_64.{repo}_1776_{name}:latest",
        )
    )

async def run(cmd):
    start = time.time()
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["bash", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print('STDOUT', e.stdout)
        print('STDERR', e.stderr)
        raise e
    tqdm.write(f'{time.time() - start:.2f}s {cmd}')
    
async def run_output(cmd):
    return await asyncio.to_thread(
        subprocess.check_output,
        ['bash', '-c', cmd],
        text=True,
    )


async def build_base(layout):
    verified = datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
    instances_by_repo = defaultdict(list)

    for instance in verified:
        repo, name = instance["instance_id"].split("__")
        instances_by_repo[repo].append(
            (
                instance["instance_id"],
                f"docker.io/swebench/sweb.eval.x86_64.{repo}_1776_{name}:latest",
            )
        )
        
    bases = []

    for repo in instances_by_repo.keys():
        instances = instances_by_repo[repo]
        instances.sort(key=lambda x: int(x[0].split("-")[-1]))
        bases.append(instances[0][1])
        
    id = uuid.uuid4()
    bundle_dir = Path(__file__).parent / 'bundles' / f'{id}'    
    layout_dir = Path(layout)
    
    await run(f"sudo rm -rf {layout_dir}")
    await run(f"sudo umoci init --layout {layout_dir}")
    await run(f"sudo umoci new --image {layout_dir}:base")

    await run(f"sudo umoci unpack --image {layout_dir}:base {bundle_dir}")
    
    for image in bases:
        await run(f"sudo podman image exists {image} || podman pull {image}")
        cid_original = (await run_output(f"sudo podman create {image} sleep infinity")).strip()
        mnt_original = (await run_output(f"sudo podman mount {cid_original}")).strip()
        
        await run(f"sudo podman start {cid_original}")
        await run(f"sudo podman exec {cid_original} bash -c 'rm -rf /opt/miniconda3/pkgs/ && rm -rf /miniconda.sh && rm -rf /root/.cache/pip/ && rm -rf /testbed'")
        await run(f"sudo podman pause {cid_original}")
        await run(f"sudo rsync -rlpgoD --checksum '{mnt_original}/' '{bundle_dir}/rootfs/'")
        await run(f"sudo podman rm -f {cid_original}")
        
    await run(f"sudo umoci repack --compress=none --image {layout_dir}:base {bundle_dir}")

async def build_chain(instances, pbar: tqdm, sbar: tqdm, base_image="sweb-base"):
    id = uuid.uuid4()
    bundle_dir = Path(__file__).parent / 'bundles' / f'{id}'    
    layout_dir = Path(__file__).parent / 'layouts' / f'{id}'    
    
    await run(f"sudo rm -rf {layout_dir}")
    await run(f"sudo umoci init --layout {layout_dir}")
    await run(f"sudo skopeo copy --dest-oci-accept-uncompressed-layers oci:{LAYOUT}:base oci:{layout_dir}:base")
    await run(f"sudo umoci unpack --image {layout_dir}:{base_image} {bundle_dir}")
        
    last_size = int(await run_output(f"du -sb {layout_dir} | cut -f1"))

    for idx, (instance_id, image) in enumerate(instances):
        new_image_name = f"{NAMESPACE}/{image.split('/')[-1].split(':')[0]}"
        tqdm.write(f"[{idx + 1}/{len(instances)}] Processing {instance_id}")

        await run(f"sudo podman image exists {image} || podman pull {image}")
        cid_original = (await run_output(f"sudo podman create {image} sleep infinity")).strip()
        mnt_original = (await run_output(f"sudo podman mount {cid_original}")).strip()
        
        await run(f"sudo podman start {cid_original}")
        await run(f"sudo podman exec {cid_original} bash -c 'rm -rf /opt/miniconda3/pkgs/ && rm -rf /miniconda.sh && rm -rf /root/.cache/pip/'")
        
        await run(f"sudo podman exec {cid_original} bash -c 'mv .git/objects/pack/ /tmp/pack/'")
        await run(f"sudo [ -d \"{bundle_dir}/rootfs/testbed/.git/objects/pack/\" ] && sudo rsync -a --delete --checksum '{bundle_dir}/rootfs/testbed/.git/objects/pack/' '{mnt_original}/testbed/.git/objects/pack/' || true")
        await run(f"sudo podman exec {cid_original} bash -c 'git unpack-objects < /tmp/pack/*.pack && git repack && git prune-packed && rm -rf /tmp/pack/'")
        
        await run(f"sudo podman pause {cid_original}")
        await run(f"sudo rsync -rlpgoD --delete --checksum '{mnt_original}/' '{bundle_dir}/rootfs/'")
        
        # Adjust config to match original image
        original_config = json.loads(await run_output(f"sudo podman inspect --format '{{{{json .Config}}}}' {image}"))
        original_cmd = original_config["Cmd"]
        original_env = original_config["Env"]
        original_workingdir = original_config["WorkingDir"]
        
        await run(f"sudo umoci repack --compress=none --refresh-bundle --image {layout_dir}:{new_image_name} {bundle_dir}")
        await run(f"sudo umoci config --image {layout_dir}:{new_image_name} --clear config.env")
        for env in original_env:
            await run(f"sudo umoci config --image {layout_dir}:{new_image_name} --config.env {env}")
        
        await run(f"sudo umoci config --image {layout_dir}:{new_image_name} --clear config.cmd")
        for cmd in original_cmd:
            await run(f"sudo umoci config --image {layout_dir}:{new_image_name} --config.cmd {cmd}")
        
        await run(f"sudo umoci config --image {layout_dir}:{new_image_name} --config.workingdir {original_workingdir}")

        async with target_sem:
            await run(f"sudo skopeo copy --dest-oci-accept-uncompressed-layers oci:{layout_dir}:{new_image_name} oci:{LAYOUT}:{new_image_name}")

        asyncio.create_task(run(f"sudo podman rm -f {cid_original}"))

        size = int(await run_output(f"du -sb {layout_dir} | cut -f1"))
        added_size = size - last_size
        last_size = size
        sbar.update(added_size)

        pbar.update(1)

async def main():
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=200))

    MAX_CHAIN_LENGTH = 120
    chains = []
    
    await build_base(layout=LAYOUT)
    base_image="base"

    # Divide all instances into chains
    for repo in instances_by_repo.keys():
        instances = instances_by_repo[repo]
        instances.sort(key=lambda x: int(x[0].split("-")[-1]))
        while len(instances) > 0:
            chains.append(instances[: min(MAX_CHAIN_LENGTH, len(instances))])
            instances = instances[min(MAX_CHAIN_LENGTH, len(instances)) :]

    pbar = tqdm(desc="Instances", total=len([x for y in instances_by_repo.values() for x in y]))
    sbar = tqdm(desc="Size", unit="B", unit_scale=True, unit_divisor=1024)
    await asyncio.gather(
        *[build_chain(chain, base_image=base_image, pbar=pbar, sbar=sbar) for chain in chains]
    )


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("Re-running with sudo...")
        os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
        
    asyncio.run(main())
