"""下载 Material Design 3 所需的官方素材。

下载内容（均为可再分发的开源授权）：

* Roboto 可变字体（google/fonts，SIL Open Font License 1.1）。
* Material Symbols Outlined 可变字体与码点表
  （google/material-design-icons，Apache License 2.0）。

用法::

    python -m md3.assets.fetch [--force]
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import pathlib
import tempfile
import urllib.error
import urllib.request

from md3 import assets

_LOGGER = logging.getLogger(__name__)

_GOOGLE_FONTS_RAW = "https://raw.githubusercontent.com/google/fonts/main"
_MATERIAL_ICONS_RAW = (
    "https://raw.githubusercontent.com/google/material-design-icons/master"
)
_SYMBOLS_BASENAME = "MaterialSymbolsOutlined%5BFILL%2CGRAD%2Copsz%2Cwght%5D"
_USER_AGENT = "md3-assets-fetch/0.1 (+https://github.com/)"
_CHUNK_SIZE = 1 << 16
# TrueType / OpenType 文件头，用于识别误存的 HTML 错误页。
_FONT_MAGICS = (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf")


class AssetDownloadError(RuntimeError):
    """素材下载失败或内容校验不通过。"""


@dataclasses.dataclass(frozen=True)
class Asset:
    """一个待下载的素材条目。

    Attributes:
        name: 便于日志阅读的名称。
        urls: 候选下载地址，按顺序尝试直到成功。
        target: 本地保存路径。
        is_font: 是否为字体文件，为真时校验文件头。
    """

    name: str
    urls: tuple[str, ...]
    target: pathlib.Path
    is_font: bool = False


ASSETS: tuple[Asset, ...] = (
    Asset(
        name="Roboto 可变字体",
        urls=(
            f"{_GOOGLE_FONTS_RAW}/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
            f"{_GOOGLE_FONTS_RAW}/apache/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
        ),
        target=assets.ROBOTO_FONT_FILE,
        is_font=True,
    ),
    Asset(
        name="Roboto 许可证",
        urls=(
            f"{_GOOGLE_FONTS_RAW}/ofl/roboto/OFL.txt",
            f"{_GOOGLE_FONTS_RAW}/apache/roboto/LICENSE.txt",
        ),
        target=assets.LICENSES_DIR / "Roboto-LICENSE.txt",
    ),
    Asset(
        name="Material Symbols Outlined 可变字体",
        urls=(f"{_MATERIAL_ICONS_RAW}/variablefont/{_SYMBOLS_BASENAME}.ttf",),
        target=assets.MATERIAL_SYMBOLS_FONT_FILE,
        is_font=True,
    ),
    Asset(
        name="Material Symbols 码点表",
        urls=(
            f"{_MATERIAL_ICONS_RAW}/variablefont/"
            f"{_SYMBOLS_BASENAME}.codepoints",
        ),
        target=assets.MATERIAL_SYMBOLS_CODEPOINTS_FILE,
    ),
    Asset(
        name="Material Symbols 许可证",
        urls=(f"{_MATERIAL_ICONS_RAW}/LICENSE",),
        target=assets.LICENSES_DIR / "MaterialSymbols-LICENSE.txt",
    ),
)


def _download(url: str, target: pathlib.Path, is_font: bool) -> None:
    """把 url 的内容下载到 target，先写临时文件再原子替换。

    Raises:
        AssetDownloadError: 网络错误、HTTP 错误或字体文件头校验失败。
    """
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".part")
    tmp_path = pathlib.Path(tmp_name)
    try:
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            open(tmp_fd, "wb") as stream,
        ):
            total = response.headers.get("Content-Length")
            received = 0
            first_chunk = True
            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                if first_chunk and is_font:
                    if not chunk.startswith(_FONT_MAGICS):
                        raise AssetDownloadError(
                            f"{url} 返回的内容不是字体文件"
                        )
                    first_chunk = False
                stream.write(chunk)
                received += len(chunk)
            _LOGGER.debug("已接收 %d / %s 字节", received, total or "?")
        tmp_path.replace(target)
    except (urllib.error.URLError, OSError) as exc:
        raise AssetDownloadError(f"下载 {url} 失败: {exc}") from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def fetch_asset(asset: Asset, force: bool = False) -> bool:
    """下载单个素材，依次尝试所有候选地址。

    Args:
        asset: 素材条目。
        force: 为真时即使本地已存在也重新下载。

    Returns:
        是否实际发生了下载（已存在且未强制时返回 False）。

    Raises:
        AssetDownloadError: 所有候选地址均失败。
    """
    if asset.target.is_file() and not force:
        _LOGGER.info("跳过 %s（已存在）", asset.name)
        return False
    errors: list[str] = []
    for url in asset.urls:
        _LOGGER.info("下载 %s <- %s", asset.name, url)
        try:
            _download(url, asset.target, asset.is_font)
        except AssetDownloadError as exc:
            errors.append(str(exc))
            continue
        _LOGGER.info(
            "完成 %s（%.1f KB）",
            asset.name,
            asset.target.stat().st_size / 1024,
        )
        return True
    raise AssetDownloadError(
        f"{asset.name} 的所有候选地址均失败:\n" + "\n".join(errors)
    )


def fetch_all(force: bool = False) -> list[str]:
    """下载全部素材。

    Args:
        force: 为真时重新下载已存在的文件。

    Returns:
        下载失败的素材名称列表；为空表示全部成功。
    """
    failures: list[str] = []
    for asset in ASSETS:
        try:
            fetch_asset(asset, force=force)
        except AssetDownloadError as exc:
            _LOGGER.error("%s", exc)
            failures.append(asset.name)
    return failures


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    Args:
        argv: 命令行参数，为 None 时使用 sys.argv。

    Returns:
        进程退出码，0 表示全部成功。
    """
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", maxsplit=1)[0]
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="重新下载已存在的文件",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出调试日志",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    failures = fetch_all(force=args.force)
    if failures:
        _LOGGER.error("以下素材下载失败: %s", ", ".join(failures))
        return 1
    _LOGGER.info("全部素材已就绪: %s", assets.ASSETS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
