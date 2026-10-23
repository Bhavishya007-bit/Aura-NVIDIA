"""Authored synthetic reference case; execute only through the trusted test guest."""
import json


def linear_search(values, target):
    visited = []
    for index, value in enumerate(values):
        visited.append(index)
        if value == target:
            return index, visited
    return -1, visited


def binary_search(values, target):
    assert values == sorted(values)
    low, high = 0, len(values) - 1
    trace = []
    while low <= high:
        mid = (low + high) // 2
        value = values[mid]
        branch = 'found' if value == target else 'right' if value < target else 'left'
        trace.append({'low': low, 'high': high, 'mid': mid, 'value': value, 'branch': branch})
        if branch == 'found':
            return mid, trace
        if branch == 'right':
            low = mid + 1
        else:
            high = mid - 1
    return -1, trace


values = [1, 3, 5, 7, 9, 11, 13, 15]
results = []
for target in [5, 16, 1]:
    linear_index, visited = linear_search(values, target)
    binary_index, trace = binary_search(values, target)
    assert (linear_index == -1) == (target not in values)
    assert (binary_index == -1) == (target not in values)
    assert linear_index == -1 or values[linear_index] == target
    assert binary_index == -1 or values[binary_index] == target
    results.append({'target': target, 'linear_index': linear_index,
                    'binary_index': binary_index, 'linear_inspected': len(visited),
                    'binary_probes': len(trace), 'linear_visited': visited,
                    'binary_trace': trace})

duplicates = [1, 3, 3, 3, 9]
duplicate_index, duplicate_trace = binary_search(duplicates, 3)
assert duplicates[duplicate_index] == 3
report = {'data_origin': 'synthetic', 'values': values,
          'count_unit': 'inspected linear items or binary midpoint probes, not all primitive comparisons',
          'timings_measured': False, 'results': results,
          'duplicates': {'values': duplicates, 'target': 3, 'index': duplicate_index,
                         'trace': duplicate_trace, 'guarantee': 'any matching index'}}
with open('search_results.json', 'w', encoding='utf-8') as handle:
    json.dump(report, handle)
print(json.dumps(report))
