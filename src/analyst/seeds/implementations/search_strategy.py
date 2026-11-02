def run(request):
    return sorted(range(len(request["rows"])), key=lambda i: request["rows"][i]["priority"])
