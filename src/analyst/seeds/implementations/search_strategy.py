import re

def run(request):
    query_tokens = re.findall(r'\b\w+\b', request["query"].lower())

    result = []

    for i, row in enumerate(request["rows"]):
        row_tokens = re.findall(r'\b\w+\b', (row['title'] + ' ' + row['text']).lower())

        overlap_count = len(set(query_tokens) & set(row_tokens))

        result.append((overlap_count, row['priority'], i))

    sorted_result = sorted(result, key=lambda x: (-x[0], x[1], x[2]))

    sorted_indices = [index for _, _, index in sorted_result]

    return sorted_indices
