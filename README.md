# SWE Bench Verified (Compressed)

Fed up by setting up all the SWE Bench Verified images? No more!

- ~~206~~ 31 GiB of total storage
- ~~100~~ 5 GiB of network transfer
- < 5min setup

## Getting the Images

The images will be named like this `logicstar/sweb.eval.x86_64.<repo>_1776_<instance>`.

### Docker
```bash
curl -L -#  https://huggingface.co/LogicStar/SWE-Bench-Verified-Compressed/resolve/main/saved.tar.zst?download=true | zstd -d --long=31 --stdout | docker load 
```

### Podman
For some reason Podman refuses to load `docker-archive`s with manifests larger than a MiB. We had to split it in two :(
```bash
curl -L -#  https://huggingface.co/LogicStar/SWE-Bench-Verified-Compressed/resolve/main/saved.1.tar.zst?download=true | zstd -d --long=31 --stdout | podman load 
curl -L -# https://huggingface.co/LogicStar/SWE-Bench-Verified-Compressed/resolve/main/saved.2.tar.zst?download=true | zstd -d --long=31 --stdout | podman load 
```

Need it even faster? Use hf cli for faster download and pull the images directly from the OCI layout in parallel:

```bash
# Clone the repo and cd into it
hf download ...
python3 load.py
```

## Using the Images

To use our images just pass `--namespace logicstar` to the SWE Bench harness. For example:

```bash
python -m swebench.harness.run_evaluation \
    --predictions_path gold \
    --max_workers 1 \
    --run_id validate-gold \
    --namespace logicstar
```