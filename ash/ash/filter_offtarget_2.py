#!/usr/bin/env python3

import sys

if sys.version_info < (3,5):
    print("This script requires Python >= 3.5.")
    print("Current Python version is {}.".format(sys.version.split()[0]))
    sys.exit(-1)

import time, threading, traceback
from collections import defaultdict
from ash import build, target_index


def run_fetch_with_retries(results, results_lock, thread_slots, arr, c5, c10, c20, i, radius):
    try:
        t = time.time()
        r = build.fetch_with_retries(arr, c5, c10, c20)
        with results_lock:
            results[radius].append(r)
            # print("Fetched {}-element slice at {} for {} in {:3.1f} seconds."
            #      .format(len(arr), i, radius, time.time() - t))
    except:
        traceback.print_exc()
    finally:
        thread_slots.release()


def fetch_all_offtargets(all_targets, proximity_radii):
    results = defaultdict(list)
    results_lock = threading.RLock()
    # above 8 the GO server may run out of ports or something like that
    max_threads = 8
    thread_slots = threading.Semaphore(max_threads)
    # also tried 10k, 15k, and 30k; too much variance to discern any real difference
    slice_size = 20000
    for radius in proximity_radii:
        c5, c10, c20 = tuple(int(c) for c in radius.split("_"))
        assert c5 <= 5
        assert c10 <= 10
        assert c20 <= 20
        for i in range(0, len(all_targets), slice_size):
            thread_slots.acquire()
            threading.Thread(
                target=run_fetch_with_retries,
                args=[results, results_lock, thread_slots, all_targets[i:i+slice_size], c5, c10, c20, i, radius]
            ).start()
    # while True:
    #     line = proc.stderr.readline()

    #     if line != b'':
    #         print(line)

    # wait for threads to finish
    for _ in range(max_threads):
        thread_slots.acquire()
    print("Identified all offtargets for {} x {} target spheres."
          .format(len(all_targets), len(proximity_radii)))
    return results


def output(offtargets_output, results):
    bad_targets = defaultdict(list)
    for req_text in results:
        for r in results[req_text]:
            for target_response in r.text.split('\n'):
                if target_response and target_response[0] in ('A', 'C', 'G', 'T'):
                    words = target_response.split()
                    assert len(words) == 2
                    target, boolean = words
                    assert len(target) == 20
                    assert boolean in ('false', 'true')
                    if boolean == 'true':
                        bad_targets[target].append(req_text)
                        assert len(bad_targets[target]) <= 2
    with open(offtargets_output, "w") as outf:
        for target in sorted(bad_targets.keys()):
            outf.write(target + " " + " ".join(sorted(bad_targets[target])) + "\n\n")


def main():
    t = time.time()
    build.git_remove_generated_file(build.off_targets_path)
    all_targets = target_index.read_all_targets(build.all_targets_path)
    results = fetch_all_offtargets(all_targets, build.offtarget_proximity.values())
    output(build.off_targets_path, results)
    build.git_add_back_generated_file(build.off_targets_path)
    print("Completed filter_offtarget in {:3.1f} seconds.".format(time.time() - t))


if __name__ == "__main__":
    retcode = main()
    sys.exit(retcode)
