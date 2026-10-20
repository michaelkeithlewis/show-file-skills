"""JUCE ValueTree binary (LiveProfessor .rack2) reader and writer. Round-trips byte-exact.

usage: vt.py FILE.rack2      print the whole tree, one node per line, after a round-trip check

As a module: n, tail = vt.load(path); edit n (Node: .type, .props, .kids, get/set/find/walk);
vt.save(out, n, tail). Property values are (type, value) tuples: int, bool, double, str,
int64, array, bin, undef. See ../references/FORMAT.md.
"""
import struct, sys, json, base64

def rd_cint(b, i):
    n = b[i]; i += 1
    neg = n & 0x80; n &= 0x7f
    v = int.from_bytes(b[i:i+n], 'little'); i += n
    return (-v if neg else v), i

def wr_cint(v):
    neg = v < 0; v = abs(v)
    n = 0; t = v
    while t: n += 1; t >>= 8
    return bytes([n | (0x80 if neg else 0)]) + v.to_bytes(n, 'little')

def rd_str(b, i):
    j = b.index(0, i); return b[i:j].decode('utf-8'), j + 1

def rd_var(b, i):
    size, i = rd_cint(b, i)
    if size == 0: return None, i
    raw = b[i:i+size]; i += size
    return dec_var(raw), i

def dec_var(raw):
    t = raw[0]; d = raw[1:]
    if t == 1: return ('int', struct.unpack('<i', d)[0])
    if t == 2: return ('bool', True)
    if t == 3: return ('bool', False)
    if t == 4: return ('double', struct.unpack('<d', d)[0])
    if t == 5: return ('str', d[:-1].decode('utf-8'))
    if t == 6: return ('int64', struct.unpack('<q', d)[0])
    if t == 7:
        n, j = rd_cint(d, 0); out = []
        for _ in range(n):
            v, j = rd_var(d, j); out.append(v)
        return ('array', out)
    if t == 8: return ('bin', d)
    if t == 9: return ('undef', None)
    return ('raw', raw)

def enc_var(v):
    if v is None: return b'\x00'
    t, x = v
    if t == 'int': raw = b'\x01' + struct.pack('<i', x)
    elif t == 'bool': raw = b'\x02' if x else b'\x03'
    elif t == 'double': raw = b'\x04' + struct.pack('<d', x)
    elif t == 'str': raw = b'\x05' + x.encode('utf-8') + b'\x00'
    elif t == 'int64': raw = b'\x06' + struct.pack('<q', x)
    elif t == 'array': raw = b'\x07' + wr_cint(len(x)) + b''.join(enc_var(e) for e in x)
    elif t == 'bin': raw = b'\x08' + x
    elif t == 'undef': raw = b'\x09'
    else: raw = x
    return wr_cint(len(raw)) + raw

class Node:
    def __init__(s, type, props=None, kids=None):
        s.type = type; s.props = props or []; s.kids = kids or []
    def get(s, k, d=None):
        for n, v in s.props:
            if n == k: return v[1] if v else None
        return d
    def set(s, k, v):
        for idx, (n, _) in enumerate(s.props):
            if n == k: s.props[idx] = (n, v); return
        s.props.append((k, v))
    def find(s, type):
        for k in s.kids:
            if k.type == type: yield k
    def walk(s, depth=0):
        yield s, depth
        for k in s.kids: yield from k.walk(depth + 1)

def rd_node(b, i):
    t, i = rd_str(b, i)
    np_, i = rd_cint(b, i); props = []
    for _ in range(np_):
        n, i = rd_str(b, i); v, i = rd_var(b, i); props.append((n, v))
    nk, i = rd_cint(b, i); kids = []
    for _ in range(nk):
        k, i = rd_node(b, i); kids.append(k)
    return Node(t, props, kids), i

def wr_node(n):
    out = n.type.encode('utf-8') + b'\x00' + wr_cint(len(n.props))
    for k, v in n.props: out += k.encode('utf-8') + b'\x00' + enc_var(v)
    out += wr_cint(len(n.kids))
    for k in n.kids: out += wr_node(k)
    return out

def load(path):
    b = open(path, 'rb').read(); n, i = rd_node(b, 0)
    return n, b[i:]

def save(path, n, tail=b''):
    open(path, 'wb').write(wr_node(n) + tail)

def dump(n, maxval=80):
    for node, d in n.walk():
        ps = []
        for k, v in node.props:
            if v is None: s = 'None'
            elif v[0] == 'bin': s = f'<bin {len(v[1])}>'
            else: s = repr(v[1])
            if len(s) > maxval: s = s[:maxval] + '...'
            ps.append(f'{k}={s}')
        print('  ' * d + node.type + ('  ' + ' '.join(ps) if ps else ''))

if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__); sys.exit(0 if len(sys.argv) == 2 else 2)
    n, tail = load(sys.argv[1])
    assert wr_node(n) + tail == open(sys.argv[1], 'rb').read(), 'roundtrip mismatch'
    print(f'# roundtrip OK, tail {len(tail)} bytes', file=sys.stderr)
    dump(n)
