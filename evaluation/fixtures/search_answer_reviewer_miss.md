### Worked Example

We used the sorted list `[2, 5, 8, 12, 16, 23, 38, 42, 50]` (length 9) and searched for targets `[2, 23, 50, 7]` (first, middle, last, absent). The program counted comparisons for each algorithm.

### Captured Results

| Target | Linear Comparisons | Binary Comparisons |
| :----- | :----------------- | :----------------- |
| 2      | 1                  | 3                  |
| 23     | 6                  | 3                  |
| 50     | 9                  | 4                  |
| 7      | 9                  | 3                  |

The results confirm that binary search uses significantly fewer comparisons than linear search for sorted data, especially as list size grows.
