"""Unit test of load_cache_to_device_buffer_v41 against a torch reference.

Usage (inside the container): python3 test_v41_swap_kernel.py
"""

import itertools
import os
import random

import torch
from sglang.kernels.ops.kvcache.hisparse import load_cache_to_device_buffer_v41

FULL_PAGE = 256
VERIFY = os.environ.get("KERNEL_VERIFY", "0") == "1"
LAYOUTS = {"v4": (576, 8), "v41": (512, 16), "v41_fp4": (256, 32)}


def page_bytes(slots, data_bytes, scale_bytes):
    return -(-slots * (data_bytes + scale_bytes) // data_bytes) * data_bytes


def row(buf_page, slot, slots, data_bytes, scale_bytes):
    data = buf_page[slot * data_bytes : (slot + 1) * data_bytes]
    base = slots * data_bytes + slot * scale_bytes
    return torch.cat([data, buf_page[base : base + scale_bytes]])


def run_case(ratio, layout, hot, bs, real, seed, top_k=512, block_size=512):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    data_bytes, scale_bytes = LAYOUTS[layout]
    slots = FULL_PAGE // ratio
    pbytes = page_bytes(slots, data_bytes, scale_bytes)
    dev = torch.device("cuda")

    rows, ctx = 6, 16384
    num_dev_pages, num_host_pages, host_layers, layer = 400, 200, 3, 1
    device_buffer = torch.randint(0, 255, (num_dev_pages, pbytes), dtype=torch.uint8, device=dev)
    host = torch.empty((num_host_pages, host_layers, pbytes), dtype=torch.uint8, pin_memory=True)
    host.copy_(torch.randint(0, 255, host.shape, dtype=torch.uint8))
    host_binding = torch.tensor(
        [host.data_ptr() + layer * pbytes, host_layers * pbytes], dtype=torch.int64, device=dev
    )

    req_to_token = torch.full((rows, ctx), -1, dtype=torch.int32)
    host_locs = torch.full((rows, ctx), -1, dtype=torch.int32)
    hot_slots = torch.full((rows, hot), -1, dtype=torch.int32)
    free_dev_pages = list(range(1, num_dev_pages))
    rng.shuffle(free_dev_pages)
    free_host_pages = list(range(num_host_pages))
    rng.shuffle(free_host_pages)
    req_ids = rng.sample(range(rows), bs)
    seq_lens = []
    for r in req_ids:
        length = rng.randint(4000, 12000)
        seq_lens.append(length)
        for p in range((length + FULL_PAGE - 1) // FULL_PAGE):
            start = p * FULL_PAGE
            n = min(FULL_PAGE, length - start)
            if rng.random() < 0.6 and free_host_pages:
                hp = free_host_pages.pop()
                host_locs[r, start : start + n] = hp * FULL_PAGE + torch.arange(n, dtype=torch.int32)
            else:
                dp = free_dev_pages.pop()
                req_to_token[r, start : start + n] = dp * FULL_PAGE + torch.arange(n, dtype=torch.int32)
        hot_pages = [free_dev_pages.pop() for _ in range(-(-hot * ratio // FULL_PAGE))]
        full = torch.cat([p * FULL_PAGE + torch.arange(FULL_PAGE, dtype=torch.int32) for p in hot_pages])
        hot_slots[r] = (full[::ratio] // ratio)[:hot]

    compressed = torch.tensor([s // ratio for s in seq_lens], dtype=torch.int32)
    tops = []
    for clen in compressed.tolist():
        k = min(top_k, clen)
        sel = torch.tensor(rng.sample(range(clen), k), dtype=torch.int32)
        tops.append(torch.cat([sel, torch.full((top_k - k,), -1, dtype=torch.int32)]))
    top_k_tokens = torch.stack(tops)

    residency = torch.full((rows, hot), -1, dtype=torch.int32, device=dev)
    lru = torch.arange(hot, dtype=torch.int16).repeat(rows, 1).to(dev)
    out = torch.full((bs, top_k + 64), -7, dtype=torch.int32, device=dev)
    num_real = torch.tensor([real], dtype=torch.int32, device=dev)
    errors = torch.zeros(3, dtype=torch.int64, device=dev)
    args = {
        "compressed_seq_lens": compressed.to(dev),
        "req_pool_indices": torch.tensor(req_ids, dtype=torch.int64, device=dev),
        "req_to_token": req_to_token.to(dev),
        "host_locs": host_locs.to(dev),
        "hot_slots": hot_slots.to(dev),
        "residency": residency,
        "lru_slots": lru,
        "host_binding": host_binding,
        "device_buffer": device_buffer,
        "top_k_device_locs": out,
        "num_real_reqs": num_real,
        "stats": errors,
        "num_top_k": top_k,
        "compress_ratio": ratio,
        "data_bytes": data_bytes,
        "scale_bytes": scale_bytes,
        "page_size": slots,
        "verify": VERIFY,
        "block_size": block_size,
    }

    def check(top, first_out=None):
        load_cache_to_device_buffer_v41(top_k_tokens=top.to(dev), **args)
        torch.cuda.synchronize()
        o = out.cpu()
        buf = device_buffer.cpu()
        hits = 0
        for b, r in enumerate(req_ids):
            if b >= real:
                assert (o[b, :top_k] == -1).all(), "padded row not invalid"
                continue
            assert (o[b, top_k:] == -7).all(), "kernel wrote past num_top_k"
            hot_set = set(hot_slots[r].tolist())
            used = []
            for i in range(top_k):
                pos = int(top[b, i])
                got = int(o[b, i])
                if pos < 0:
                    assert got == -1
                    continue
                full_pos = pos * ratio
                if req_to_token[r, full_pos] >= 0:
                    assert got == int(req_to_token[r, full_pos]) // ratio, (b, i, pos, got)
                    continue
                assert got in hot_set, (b, i, pos, got)
                used.append(got)
                host_row = int(host_locs[r, full_pos]) // ratio
                want = row(host[host_row // slots, layer], host_row % slots, slots, data_bytes, scale_bytes)
                have = row(buf[got // slots], got % slots, slots, data_bytes, scale_bytes)
                assert torch.equal(want, have), f"row mismatch b={b} pos={pos}"
                if first_out is not None and pos in first_out[b]:
                    hits += first_out[b][pos] == got
            assert len(used) == len(set(used)), "two positions share a hot slot"
        assert int(errors[0].item()) == 0
        return o, hits

    o1, _ = check(top_k_tokens)
    # Cold hot buffers: every demoted selection of a real row is a copy.
    demoted = sum(
        int(req_to_token[r, int(p) * ratio] < 0)
        for b, r in enumerate(req_ids[:real])
        for p in top_k_tokens[b].tolist()
        if p >= 0
    )
    assert int(errors[1].item()) == demoted, (int(errors[1].item()), demoted)
    assert int(errors[2].item()) == 0, int(errors[2].item())
    first = [
        {int(top_k_tokens[b, i]): int(o1[b, i]) for i in range(top_k) if top_k_tokens[b, i] >= 0}
        for b in range(bs)
    ]
    # Keep half of each selection and draw the rest anew: kept demoted positions must hit.
    top2 = top_k_tokens.clone()
    for b in range(bs):
        clen = int(compressed[b])
        keep = top2[b, : top_k // 2]
        pool = sorted(set(range(clen)) - set(keep.tolist()))
        k = min(top_k - top_k // 2, len(pool))
        top2[b, top_k // 2 : top_k // 2 + k] = torch.tensor(rng.sample(pool, k), dtype=torch.int32)
    _, hits = check(top2, first)
    return hits


def main():
    total = 0
    for ratio, layout, hot, (bs, real), block in itertools.product(
        (1, 2), ("v4",), (512, 1024, 2048), ((4, 4), (5, 3)), (512, 960, 1024)
    ):
        hits = run_case(ratio, layout, hot, bs, real, seed=ratio * 7 + hot + bs, block_size=block)
        total += 1
        print(f"ok ratio={ratio} layout={layout} hot={hot} bs={bs} real={real} block={block} second-call hits={hits}")
    print(f"all {total} cases passed")


if __name__ == "__main__":
    main()
