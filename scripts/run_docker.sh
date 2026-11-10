#!/usr/bin/env bash
# Start a ROCm container for Petra, or get back into it, and open a root shell in its /workspace
# (README step 2).
#
#   scripts/run_docker.sh                                # the newest daily sglang image, ROCm 10, MI35x
#   IMAGE_VARIANT=rocm10-mi30x scripts/run_docker.sh     # the newest one for another GPU or ROCm
#   IMAGE=rocm/sgl-dev:<tag> NAME=<name> scripts/run_docker.sh
#   DOCKER_SOCKET=1 scripts/run_docker.sh                # also mount the host's Docker socket
#   bash <(curl -fsSL https://raw.githubusercontent.com/At1a8/Petra/main/scripts/run_docker.sh)   # no checkout
#
# Each container keeps its own /workspace, where Petra and its runs live, and its own copy of the image's
# /sgl-workspace/sglang, the code tasks change: apart from every other container's, for as long as the
# container exists. A new container starts from the newest daily image, pulled at its first use. A
# container named NAME is never removed: run again, this starts it if it was stopped and opens a shell in
# it, /workspace as it was left, and says so when its image is no longer the newest daily one (tasks there
# stop at Setup to ask). A new task gets a new container under another NAME; `docker rm -f <name>`
# removes one you are done with, and its /workspace with it. Your Claude Code, its state and your keys
# stay in your home on the host, mounted at the same path and named in PETRA_HOST_HOME. Run README step
# 3 once in every new container.
#
# The host's Docker socket is not mounted by default: Petra's agents run as root with permissions
# auto-approved, and the socket would let them stop or start any container on the host. Petra inside the
# container does not need it.
VARIANT=${IMAGE_VARIANT:-rocm10-mi35x}
NAME=${NAME:-${SUDO_USER:-$USER}}
HOST_HOME=$HOME
[ -n "$SUDO_USER" ] && HOST_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
SUDO=$([ -w /var/run/docker.sock ] || echo sudo)
RAW=https://raw.githubusercontent.com/At1a8/Petra/main/scripts

latest_image() {  # scripts/latest_image.py next to this script, else the one on GitHub
  if [ -f "$(dirname "$0")/latest_image.py" ]; then
    python3 "$(dirname "$0")/latest_image.py" "$@"
  else
    curl -fsSL "$RAW/latest_image.py" | python3 - "$@"
  fi
}

if OLD=$($SUDO docker inspect -f '{{.Config.Image}}' "$NAME" 2>/dev/null); then
  if [ -n "$IMAGE" ] && [ "$IMAGE" != "$OLD" ]; then
    echo "run_docker.sh: container $NAME runs $OLD, not $IMAGE. Pick another NAME, or remove it first" \
      "(\`${SUDO:+sudo }docker rm -f $NAME\`, which deletes its /workspace)" >&2
    exit 1
  fi
  echo "run_docker.sh: back into container $NAME ($OLD), /workspace as it was left" >&2
  CMP=$(latest_image --compare "$OLD" 2>/dev/null)
  case "$CMP" in
    older\ *) echo "run_docker.sh: $OLD is not the newest daily image any more; that is ${CMP#older }. Tasks in" \
                "this container stop at Setup to ask. For the newest sglang, start a new container:" \
                "NAME=$NAME-$(date +%m%d) $0 (or remove this one first: \`${SUDO:+sudo }docker rm -f $NAME\`," \
                "which deletes its /workspace)" >&2 ;;
  esac
  $SUDO docker start "$NAME" >/dev/null || exit 1
  exec $SUDO docker exec -it -w /workspace "$NAME" bash
fi

if [ -z "$IMAGE" ]; then
  IMAGE=$(latest_image --variant "$VARIANT")
  if [ -z "$IMAGE" ]; then
    IMAGE=$($SUDO docker images --format '{{.Repository}}:{{.Tag}}' rocm/sgl-dev |
      grep -E ":v[0-9][0-9a-z.]*-$VARIANT-[0-9]{8}\$" | awk -F- '{print $NF, $0}' | sort | tail -n 1 | cut -d' ' -f2)
    [ -n "$IMAGE" ] && echo "run_docker.sh: Docker Hub not reachable; using the newest local image" >&2
  fi
  [ -n "$IMAGE" ] || { echo "run_docker.sh: no $VARIANT image found; set IMAGE=rocm/sgl-dev:<tag>" >&2; exit 1; }
fi
echo "run_docker.sh: new container $NAME from $IMAGE" >&2

MOUNTS=()
for d in /home /data /data2 /apps /mnt /shared /nfs_shared1 /kmd2 $EXTRA_MOUNTS; do
  [ -d "$d" ] && MOUNTS+=(-v "$d:$d")
done
[ "$DOCKER_SOCKET" = 1 ] && MOUNTS+=(-v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro)

exec $SUDO docker run -it \
  --privileged --ipc=host --network=host --device=/dev/kfd --device=/dev/dri --group-add video \
  --cap-add=SYS_PTRACE --security-opt seccomp=unconfined -w /workspace \
  "${MOUNTS[@]}" \
  -e PYTHONDONTWRITEBYTECODE=1 -e DISABLE_AUTOUPDATER=1 -e PETRA_IMAGE="$IMAGE" -e PETRA_CONTAINER="$NAME" \
  -e PETRA_HOST_HOME="$HOST_HOME" \
  --shm-size=512G --ulimit memlock=-1 --ulimit stack=67108864 \
  --entrypoint /bin/bash --name "$NAME" "$IMAGE"
