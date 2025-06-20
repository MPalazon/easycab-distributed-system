import functools
STX, ETX, ENQ, ACK, NACK = b'\x02', b'\x03', b'\x05', b'\x06', b'\x15'
def calculate_lrc(m: bytes) -> bytes: return functools.reduce(lambda a,b: a^b, m).to_bytes(1,'big')
def wrap_message(r: str) -> bytes: m = r.encode('utf-8'); return STX + m + ETX + calculate_lrc(m)
def unwrap_message(d: bytes) -> tuple[str, bool]:
    if not d.startswith(STX) or (etx_pos := d.find(ETX)) == -1 or len(d) < etx_pos + 2: return "Formato inválido", False
    message_bytes = d[1:etx_pos]
    if d[etx_pos + 1:etx_pos + 2] != calculate_lrc(message_bytes): return "Error de LRC", False
    return message_bytes.decode('utf-8'), True