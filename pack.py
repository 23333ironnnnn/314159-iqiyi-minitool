"""把已构建的离线 H5 打包为爱奇艺互动小应用 ZIP。只依赖 Python 3.9+。"""

import argparse
import os
import posixpath
import re
import shutil
import stat
import tempfile
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


LIMIT = 20_000_000  # 平台写作 20 MB，按十进制字节检查。
EXAMPLE = Path(__file__).resolve().parent / "example"
COMMON_DEV_FILES = {
    "node_modules", "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "AGENTS.md", "SKILL.md", "README.md", "发布填写单.md", "校验摘要.txt",
}
CSS_REF = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)|@import\s+['"]([^'"]+)['"]""", re.I | re.S)
JS_REF = re.compile(r"""\b(fetch|import|importScripts|new\s+(?:WebSocket|EventSource|Worker))\s*\(\s*(['"])([^'"\r\n]+)\2\s*(?=[,)])""")


def check_ref(raw, page, names):
    ref = raw.strip()
    if not ref or ref.startswith("#"):
        return
    url = urlsplit(ref)
    if url.scheme.lower() in {"data", "blob"}:
        return
    if url.scheme or url.netloc or ref.startswith(("/", "\\")):
        raise ValueError(f"{page} 引用了外部地址或根路径，请改用包内相对路径：{ref[:120]}")
    path = unquote(url.path)
    if path:
        dest = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
        if dest not in names:
            raise ValueError(f"{page} 找不到资源：{ref[:120]}")


def check_css(code, page, names):
    for match in CSS_REF.finditer(re.sub(r"/\*.*?\*/", "", code, flags=re.S)):
        check_ref(match[2] if match[2] is not None else match[3], page, names)


def check_js(code, page, names, inline=False):
    for match in JS_REF.finditer(code):
        ref = match[3]
        # 外置脚本中的 fetch/Worker 相对于加载它的文档，可能被多个页面共享。
        if inline or match[1] in {"import", "importScripts"} or urlsplit(ref).scheme or ref.startswith(("/", "\\")):
            check_ref(ref, page, names)


class Page(HTMLParser):
    def __init__(self, name, names):
        super().__init__()
        self.name, self.names = name, names
        self.context = None

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.context = tag
        for key, value in attrs:
            if not value:
                continue
            if tag == "base" and key == "href" and value != "./":
                raise ValueError(f"{self.name} 请将 base href 调为 ./ 或移除并使用相对路径")
            if tag == "base" and key == "href":
                continue
            if key in {"src", "href", "xlink:href", "poster", "action", "formaction"} or (tag == "object" and key == "data"):
                check_ref(value, self.name, self.names)
            elif key == "style":
                check_css(value, self.name, self.names)

    def handle_data(self, data):
        if self.context == "style":
            check_css(data, self.name, self.names)
        elif self.context == "script":
            check_js(data, self.name, self.names, inline=True)

    def handle_endtag(self, tag):
        if tag == self.context:
            self.context = None


def collect(source):
    files = {}
    seen = set()
    if not (source / "index.html").is_file():
        raise ValueError("请传入构建目录，根目录须有 index.html")
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if any(p in {".DS_Store", "__MACOSX"} or p.startswith("._") for p in rel.parts):
            continue
        name = rel.as_posix()
        if path.is_symlink() or any(p.startswith(".") or p in COMMON_DEV_FILES for p in rel.parts):
            raise ValueError(f"发现开发文件、隐藏项或软链接，请只传游戏构建目录：{name}")
        if "\\" in name or ":" in name or any(ord(c) < 32 for c in name):
            raise ValueError(f"请修改异常文件名：{name!r}")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise ValueError(f"路径重名，请检查大小写或字符编码：{name}")
        seen.add(key)
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat().st_mode) or path.suffix.lower() in {".zip", ".pem", ".key", ".map", ".md"}:
            raise ValueError(f"请将非运行文件移出构建目录：{name}")
        files[name] = path
    if "index.html" not in files or not files["index.html"].stat().st_size:
        raise ValueError("入口文件须命名为 index.html，且包含页面内容")
    for name, path in files.items():
        suffix = path.suffix.lower()
        if suffix in {".htm", ".html", ".css", ".js", ".mjs", ".svg"}:
            try:
                body = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                raise ValueError(f"请将 {name} 转存为 UTF-8") from None
            if suffix in {".htm", ".html", ".svg"}:
                doc = Page(name, files)
                doc.feed(body)
                doc.close()
            elif suffix == ".css":
                check_css(body, name, files)
            else:
                check_js(body, name, files)
    return files


def pack(source, output):
    source, output = source.resolve(), output.absolute()
    if output.suffix.lower() != ".zip" or source in output.resolve().parents:
        raise ValueError("输出须为构建目录之外的 .zip 文件")
    files = collect(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        temp = Path(scratch) / "game.zip"
        with ZipFile(temp, "w", ZIP_DEFLATED) as archive:
            for name, path in files.items():
                info = ZipInfo(name)
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with path.open("rb") as inp, archive.open(info, "w") as out:
                    shutil.copyfileobj(inp, out)
                if temp.stat().st_size > LIMIT:
                    raise ValueError("ZIP 超过 20 MB，请先压缩游戏资源")
        size = temp.stat().st_size
        if size > LIMIT:
            raise ValueError("ZIP 超过 20 MB，请先压缩游戏资源")
        with ZipFile(temp) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(files):
                raise ValueError("ZIP 内容校验失败")
        try:
            os.link(temp, output)
        except FileExistsError:
            if output.is_symlink() or not output.is_file() or output.stat().st_size != size or output.read_bytes() != temp.read_bytes():
                raise ValueError(f"已有同名文件，请指定新的 ZIP 路径：{output}") from None
    print(f"打包通过 · {len(files)} 个文件 · {size:,} 字节\n{output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=EXAMPLE, help="游戏构建目录，省略则打包示例")
    parser.add_argument("-o", "--output", type=Path, default=Path("iqiyi-app.zip"), help="输出 ZIP 路径")
    args = parser.parse_args()
    try:
        pack(args.source, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"打包失败：{exc}\n")
