import subprocess
import datasets
import asyncio
import click

from collections import defaultdict
from tqdm import tqdm


pull_semaphore = asyncio.Semaphore(500)

async def pull(layout, image_name, root):
    await asyncio.to_thread(
        subprocess.check_call,
        [
            "podman",
            *(["--root", root] if root else []),
            "--storage-opt", "ignore_chown_errors=true",
            "pull",
            "-q",
            f"oci:{layout}:{image_name}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
        

async def worker(pbar, images, layout, root):
    while len(images) > 0:
        
        image_name = images.pop()
        tqdm.write(image_name)
    
        try:
            async with pull_semaphore:
                await pull(layout, image_name, root)
        except subprocess.CalledProcessError as e:
            print(e.stdout)
            print(e.stderr)
            print(e)
            break
        finally:
            pbar.update(1)

async def main(layout, root):    
    verified = datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")

    images = []
    images_by_repo = defaultdict(list)
    for instance in verified:
        repo, name = instance["instance_id"].split("__")
        images_by_repo[repo].append(f"logicstar/sweb.eval.x86_64.{repo}_1776_{name}")

    pbar = tqdm(total=len(verified))
        
    tqdm.write("Moving all the images to local container storage, this should take <5min. First few images are slower than the rest...")
    tqdm.write("Moving the base layer to storage, might take up to a minute...")
    await pull(layout, list(images_by_repo.values())[0][0], root)

    workers = []
    for repo, images in images_by_repo.items():
        workers.append(worker(
            pbar,
            sorted(images, key=lambda x: -int(x.split('-')[-1].split(':')[0])),
            layout,
            root
        ))

    await asyncio.gather(*workers)


@click.command()
@click.option(
    "--layout",
    default="./layout",
    show_default=True,
help="Path to layout directory."
)
@click.option(
    "--root",
    default=None,
    help="Path to podman root."
)
def cli(layout, root):
    asyncio.run(main(layout, root))

if __name__ == "__main__":
    cli()
