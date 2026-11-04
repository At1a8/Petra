#!/usr/bin/env bash
# Start a fresh ROCm container for Petra and open a root shell in it (README step 2).
#
#   IMAGE=rocm/sgl-dev:<tag> NAME=<name> scripts/run_docker.sh
#
# It removes the previous container of the same name first, so nothing installed inside a container
# survives the next run: Claude Code, the checkouts and your keys live on the host under /home, which is
# mounted at the same path. Run README step 3 in every new container.
IMAGE=${IMAGE:-rocm/sgl-dev:v0.5.22-rocm10-mi35x-20261021}
NAME=${NAME:-$USER}
SUDO=$([ -w /var/run/docker.sock ] || echo sudo)

MOUNTS=()
for d in /home /data /data2 /apps /mnt /shared /nfs_shared1 /kmd2 $EXTRA_MOUNTS; do
  [ -d "$d" ] && MOUNTS+=(-v "$d:$d")
done

$SUDO docker stop "$NAME" >/dev/null 2>&1
$SUDO docker rm "$NAME" >/dev/null 2>&1
exec $SUDO docker run -it \
  --privileged --ipc=host --network=host --device=/dev/kfd --device=/dev/dri --group-add video \
  --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
  -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro -w /workspace \
  "${MOUNTS[@]}" \
  -e PYTHONDONTWRITEBYTECODE=1 -e DISABLE_AUTOUPDATER=1 \
  --shm-size=512G --ulimit memlock=-1 --ulimit stack=67108864 \
  --entrypoint /bin/bash --name "$NAME" "$IMAGE"
