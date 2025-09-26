rm -rf out || true
mkdir -p out

# Package layout: layout.tar.zst
python3 compress.py

# Layout -> Podman
python3 load.py

# Package docker-archive: saved.tar.zst, saved.1.tar.zst, saved.2.tar.zst
podman save -m $(cat images.txt) | zstd -f -T100 -19 --long=31 -o out/saved.tar.zst   
podman save -m $(head -n 253 images.txt) | zstd -f -T100 -19 --long=31 -o out/saved.1.tar.zst   
podman save -m $(tail -n 247 images.txt) | zstd -f -T100 -19 --long=31 -o out/saved.2.tar.zst   
