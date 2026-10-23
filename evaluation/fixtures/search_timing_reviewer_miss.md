### Worked Example

We used a small sorted list `[1, 3, 5, 7, 9, 11, 13, 15]` and searched for targets `[7, 1, 15, 4]` (three present, one absent). Both algorithms returned identical index results.

### Results

| Target | Linear Index | Binary Index | Linear Time | Binary Time |
|---|---|---|---|---|
|7|3|3|~0.00s|~0.00s|
|1|0|0|~0.00s|~0.00s|
|15|7|7|~0.00s|~0.00s|
|4|-1|-1|~0.00s|~0.00s|

### Limitations

With only 8 elements, both searches complete in microseconds—too fast for `time.perf_counter()` to show meaningful differences.

For demonstration, binary search performs ~3 comparisons max on this list (log₂8=3), while linear search averages 4 comparisons.
