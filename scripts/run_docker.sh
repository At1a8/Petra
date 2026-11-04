#!/usr/bin/env bash
# Start a fresh ROCm container for Petra and open a root shell in it (README step 2).
#
#   scripts/run_docker.sh                                # the newest daily sglang image, ROCm 10, MI35x
#   IMAGE_VARIANT=rocm10-mi30x scripts/run_docker.sh     # the newest one for another GPU or ROCm
#   IMAGE=rocm/sgl-dev:<tag> NAME=<name> scripts/run_docker.sh
#
# Tasks test the newest sglang unless you pin IMAGE. It removes the previous container of the same name
# first, and with it anything still running there; get back into a running one with
# `docker exec -it <name> bash`. Nothing installed inside a container survives the next run: Claude
# Code, its state, the checkouts and your keys live on the host under /home, mounted at the same path.
# Run README step 3 in every new container.
VARIANT=${IMAGE_VARIANT:-rocm10-mi35x}
NAME=${NAME:-$USER}
SUDO=$([ -w /var/run/docker.sock ] || echo sudo)

if [ -z "$IMAGE" ]; then
  IMAGE=$(python3 "$(dirname "$0")/latest_image.py" --variant "$VARIANT")
  if [ -z "$IMAGE" ]; then
    IMAGE=$($SUDO docker images --format '{{.Repository}}:{{.Tag}}' rocm/sgl-dev |
      grep -E ":v[0-9][0-9a-z.]*-$VARIANT-[0-9]{8}\$" | awk -F- '{print $NF, $0}' | sort | tail -n 1 | cut -d' ' -f2)
    [ -n "$IMAGE" ] && echo "run_docker.sh: Docker Hub not reachable; using the newest local image" >&2
  fi
  [ -n "$IMAGE" ] || { echo "run_docker.sh: no $VARIANT image found; set IMAGE=rocm/sgl-dev:<tag>" >&2; exit 1; }
fi
echo "run_docker.sh: $IMAGE" >&2

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
  -e PYTHONDONTWRITEBYTECODE=1 -e DISABLE_AUTOUPDATER=1 -e PETRA_IMAGE="$IMAGE" \
  --shm-size=512G --ulimit memlock=-1 --ulimit stack=67108864 \
  --entrypoint /bin/bash --name "$NAME" "$IMAGE"
