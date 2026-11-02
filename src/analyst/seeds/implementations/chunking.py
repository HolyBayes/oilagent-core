def run(request):
    offsets, size, overlap = request["offsets"], request["size"], request["overlap"]
    spans = []
    for start in range(0, len(offsets), size - overlap):
        window = offsets[start : start + size]
        spans.append([window[0][0], window[-1][1]])
        if start + size >= len(offsets):
            break
    return spans
