"""Pre-allocation byte budget only; JSON syntax and schemas are checked separately."""


def check(data):
    if type(data) is not bytes or len(data) > 65536:
        return False
    payload = data
    depth = 0
    quoted = escaped = False
    for char in payload:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > 8:
                return False
        elif char in (93, 125):
            depth -= 1
            if depth < 0:
                return False
    return True
