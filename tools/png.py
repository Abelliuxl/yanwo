"""极简 PNG 读写（只支持 8bit RGB/RGBA，够用来分析 gamescope 截图）。

为什么自己写：本机没装 PIL/numpy，而"看画面"是验证窗口层级最真实的办法
（gamescope 只画 focus 窗 + override 窗，堆叠顺序会骗人，像素不会）。
"""
from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


def read_png(path: str | Path) -> tuple[int, int, bytes, int]:
    """返回 (宽, 高, RGBA 字节, 每像素字节数)。"""
    data = Path(path).read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG")
    pos, idat, w, h, ctype = 8, bytearray(), 0, 0, 6
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or ctype not in (2, 6) or interlace:
                raise ValueError(f"不支持的 PNG: depth={depth} ctype={ctype} interlace={interlace}")
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    bpp = 4 if ctype == 6 else 3
    raw = zlib.decompress(bytes(idat))
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    if bpp == 4:
        return w, h, bytes(out), 4
    rgba = bytearray(w * h * 4)
    for i in range(w * h):
        rgba[i * 4:i * 4 + 3] = out[i * 3:i * 3 + 3]
        rgba[i * 4 + 3] = 255
    return w, h, bytes(rgba), 4


def write_png(path: str | Path, w: int, h: int, rgba: bytes) -> None:
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]

    def chunk(typ: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + typ + body
                + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF))

    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def crop(rgba: bytes, sw: int, _sh: int, x: int, y: int, w: int, h: int) -> bytes:
    out = bytearray(w * h * 4)
    for row in range(h):
        s = ((y + row) * sw + x) * 4
        out[row * w * 4:(row + 1) * w * 4] = rgba[s:s + w * 4]
    return bytes(out)


def scale(rgba: bytes, sw: int, sh: int, nw: int, nh: int) -> bytes:
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        sy = min(sh - 1, y * sh // nh)
        for x in range(nw):
            sx = min(sw - 1, x * sw // nw)
            s = (sy * sw + sx) * 4
            d = (y * nw + x) * 4
            out[d:d + 4] = rgba[s:s + 4]
    return bytes(out)


def px(rgba: bytes, w: int, x: int, y: int) -> tuple[int, int, int]:
    i = (y * w + x) * 4
    return rgba[i], rgba[i + 1], rgba[i + 2]


if __name__ == "__main__":
    src = sys.argv[1]
    w, h, data, _ = read_png(src)
    print(f"{src}: {w}x{h}")
    for d in sys.argv[2:]:
        parts = d.split(":")
        if parts[0] == "crop":
            x, y, cw, ch = (int(v) for v in parts[1].split(","))
            dst = parts[2]
            write_png(dst, cw, ch, crop(data, w, h, x, y, cw, ch))
        else:
            nw, nh = (int(v) for v in parts[1].split(","))
            write_png(parts[2], nw, nh, scale(data, w, h, nw, nh))
        print("  ->", parts[-1])
