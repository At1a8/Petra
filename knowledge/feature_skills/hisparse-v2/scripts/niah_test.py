"""Needle-in-a-haystack client for long-context KV placement tests.

Each prompt hides "The secret key of <name> is <number>." at a random depth inside
deterministic filler text and asks for the number with greedy decoding, so a wrong
KV row anywhere in the selected context shows up as a wrong or unstable answer.

Passes resend the same prompts: the second pass hits the radix cache, and with a
small device pool it reloads prefixes that HiCache wrote back to host.

Usage (inside the container):
  python3 niah_test.py --port 30100 --num-prompts 16 --context-tokens 30000 --passes 2
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import random
import re
import time
import urllib.request

NAMES = [
    "Aurora", "Basil", "Cobalt", "Delta", "Ember", "Fjord", "Garnet", "Harbor",
    "Indigo", "Juniper", "Kestrel", "Lumen", "Meadow", "Nimbus", "Onyx", "Pebble",
    "Quartz", "Raven", "Sierra", "Thistle", "Umber", "Vesper", "Willow", "Xenon",
    "Yarrow", "Zephyr",
]

SUBJECTS = [
    "The river", "A quiet village", "The old lighthouse", "An orchard", "The market square",
    "A mountain trail", "The library", "A small harbor", "The wheat field", "An abandoned mill",
    "The night train", "A glass greenhouse", "The stone bridge", "A coastal road", "The bakery",
]
VERBS = [
    "was described in", "appeared in", "was mentioned in", "was painted in", "was recorded in",
    "was remembered in", "was photographed in", "was sketched in",
]
OBJECTS = [
    "a letter from the north", "the morning newspaper", "an old travel diary", "a school essay",
    "a weather report", "the town archive", "a forgotten postcard", "a radio broadcast",
]
DETAILS = [
    "while the wind carried the smell of rain.", "as the bells rang twice at noon.",
    "under a sky the color of slate.", "before the first frost of the season.",
    "during a long and uneventful afternoon.", "when the street lamps flickered on.",
    "while children played near the fountain.", "as fishermen returned with empty nets.",
]


def filler_sentence(rng: random.Random) -> str:
    return (
        f"{rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(OBJECTS)} "
        f"{rng.choice(DETAILS)}"
    )


def build_prompt(
    index: int, context_tokens: int, seed: int, needles: int = 1
) -> tuple[str, list[str]]:
    rng = random.Random(seed * 100003 + index)
    names = [f"{rng.choice(NAMES)}-{index}-{n}" for n in range(needles)]
    keys = [str(rng.randint(10000, 99999)) for _ in range(needles)]
    # ~14 tokens per filler sentence
    num_sentences = max(8, context_tokens // 14)
    sentences = [filler_sentence(rng) for _ in range(num_sentences)]
    # Spread the needles over the whole context, in random order.
    depths = sorted(rng.uniform(0.02, 0.98) for _ in range(needles))
    order = list(range(needles))
    rng.shuffle(order)
    for depth, n in sorted(zip(depths, order), reverse=True):
        sentences.insert(
            int(depth * num_sentences), f"The secret key of {names[n]} is {keys[n]}."
        )
    haystack = " ".join(sentences)
    if needles == 1:
        prompt = (
            "Read the following text carefully. It hides one secret key.\n\n"
            f"{haystack}\n\n"
            f"Question: What is the secret key of {names[0]}?\n"
            f"Answer: The secret key of {names[0]} is"
        )
    else:
        prompt = (
            f"Read the following text carefully. It hides {needles} secret keys.\n\n"
            f"{haystack}\n\n"
            f"Question: What are the secret keys of {', '.join(names)}? "
            "List them in this order, separated by commas.\n"
            "Answer:"
        )
    return prompt, keys


def generate(
    port: int,
    prompt: str,
    max_new_tokens: int,
    timeout: float,
    rid: str,
    logprobs: bool = False,
) -> dict:
    payload = {
        "text": prompt,
        "rid": rid,
        "sampling_params": {
            "temperature": 0.0,
            "max_new_tokens": max_new_tokens,
        },
    }
    if logprobs:
        payload["return_logprob"] = True
    body = json.dumps(payload).encode()
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


def run_pass(args, prompts, keys, pass_id: int) -> list[dict]:
    results = [None] * len(prompts)

    def work(i):
        rid = f"niah-s{args.seed}-p{pass_id}-{i}-{int(time.time() * 1000)}"
        out = generate(
            args.port, prompts[i], args.max_new_tokens, args.timeout, rid, args.logprobs
        )
        meta = out.get("meta_info", {})
        text = out.get("text", "")
        found = re.findall(r"\d{5}", text)
        want = keys[i]
        hits = sum(a == b for a, b in zip(found, want))
        return i, {
            "pass": pass_id,
            "index": i,
            "rid": rid,
            "key": want,
            "answer": found[: len(want)],
            "recalled": hits,
            "correct": hits == len(want),
            "text": text,
            "prompt_tokens": meta.get("prompt_tokens"),
            "cached_tokens": meta.get("cached_tokens"),
            "completion_tokens": meta.get("completion_tokens"),
            "latency": out["_latency"],
            **(
                {"logprobs": [t[0] for t in meta.get("output_token_logprobs", [])]}
                if args.logprobs
                else {}
            ),
        }

    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        for i, res in pool.map(work, range(len(prompts))):
            results[i] = res
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=30100)
    parser.add_argument("--num-prompts", type=int, default=16)
    parser.add_argument("--context-tokens", type=int, default=30000)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--max-new-tokens", type=int, default=16)
    parser.add_argument("--needles", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument(
        "--logprobs", action="store_true", help="record each output token's logprob"
    )
    args = parser.parse_args()

    built = [
        build_prompt(i, args.context_tokens, args.seed, args.needles)
        for i in range(args.num_prompts)
    ]
    prompts = [p for p, _ in built]
    keys = [k for _, k in built]

    all_results = []
    first_answers = None
    for pass_id in range(args.passes):
        start = time.time()
        results = run_pass(args, prompts, keys, pass_id)
        elapsed = time.time() - start
        all_results.extend(results)
        correct = sum(r["correct"] for r in results)
        recalled = sum(r["recalled"] for r in results)
        prompt_tokens = sum(r["prompt_tokens"] or 0 for r in results)
        cached = sum(r["cached_tokens"] or 0 for r in results)
        line = (
            f"pass {pass_id}: correct {correct}/{len(results)}, "
            f"recalled keys {recalled}/{len(results) * args.needles}, "
            f"prompt_tokens {prompt_tokens}, cached_tokens {cached}, "
            f"elapsed {elapsed:.1f}s"
        )
        answers = [r["text"] for r in results]
        if first_answers is None:
            first_answers = answers
        else:
            same = sum(a == b for a, b in zip(first_answers, answers))
            line += f", identical_to_pass0 {same}/{len(results)}"
        print(line, flush=True)
        wrong = [r for r in results if not r["correct"]]
        for r in wrong[:5]:
            print(
                f"  wrong idx={r['index']} key={r['key']} text={r['text']!r}",
                flush=True,
            )

    if args.out:
        with open(args.out, "w") as f:
            for r in all_results:
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
