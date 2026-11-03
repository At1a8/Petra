"""Decode-heavy long-context throughput: distinct random-token prompts, fixed output
length (ignore_eos), a bounded number of in-flight requests."""

import argparse
import concurrent.futures as cf
import json
import random
import time
import urllib.request


def generate(port: int, input_ids: list, max_new_tokens: int, timeout: float) -> dict:
    body = json.dumps(
        {
            "input_ids": input_ids,
            "sampling_params": {
                "temperature": 0.0,
                "max_new_tokens": max_new_tokens,
                "ignore_eos": True,
            },
        }
    ).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read())
    out["_latency"] = time.time() - start
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=30100)
    parser.add_argument("--num-prompts", type=int, default=32)
    parser.add_argument("--input-len", type=int, default=30000)
    parser.add_argument("--output-len", type=int, default=512)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--vocab", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    prompts = [
        [rng.randrange(1000, args.vocab) for _ in range(args.input_len)]
        for _ in range(args.num_prompts)
    ]
    start = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        outs = list(
            pool.map(
                lambda p: generate(args.port, p, args.output_len, args.timeout), prompts
            )
        )
    elapsed = time.time() - start
    out_tokens = sum(o["meta_info"]["completion_tokens"] for o in outs)
    in_tokens = sum(o["meta_info"]["prompt_tokens"] for o in outs)
    lat = sorted(o["_latency"] for o in outs)
    summary = {
        "num_prompts": args.num_prompts,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "elapsed_s": round(elapsed, 1),
        "output_tok_per_s": round(out_tokens / elapsed, 1),
        "total_tok_per_s": round((in_tokens + out_tokens) / elapsed, 1),
        "latency_p50_s": round(lat[len(lat) // 2], 1),
        "latency_max_s": round(lat[-1], 1),
    }
    print(json.dumps(summary))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(summary, f)


if __name__ == "__main__":
    main()
