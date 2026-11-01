from PIL import Image, ImageSequence

def exit_to_entrance_gif(
    exit_gif_path: str,
    entrance_gif_path: str,
    play_once: bool = True,
):
    """
    由"退出动画 GIF"生成"入场动画 GIF"（即倒放）。

    :param exit_gif_path:      模板（退出动画）路径
    :param entrance_gif_path:  输出（入场动画）路径
    :param play_once:          是否只播放一次（默认 True）
    """
    with Image.open(exit_gif_path) as im:
        frames, durations = [], []

        for frame in ImageSequence.Iterator(im):
            # 统一转 RGBA，避免调色板差异导致颜色错乱
            frames.append(frame.convert("RGBA").copy())
            # 每帧时长（毫秒），缺失时默认 100ms
            durations.append(frame.info.get("duration", im.info.get("duration", 100)))

        # 倒序帧 + 倒序时长（时长必须跟着帧一起倒，否则节奏不对）
        frames.reverse()
        durations.reverse()

        frames[0].save(
            entrance_gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=0,          # 先写 0，随后用二进制改成 1
            disposal=2,      # 每帧绘制前恢复背景，避免残影
            optimize=False,
        )

    if play_once:
        _set_loop_count(entrance_gif_path, 1)


def _set_loop_count(gif_path: str, loop_count: int = 1):
    """
    修改 GIF 的 Netscape 扩展块，把循环次数精确设为 loop_count。
    1 = 只播放一次；0 = 无限循环。
    """
    with open(gif_path, "rb") as f:
        data = bytearray(f.read())

    marker = b"NETSCAPE2.0"
    idx = data.find(marker)

    if idx != -1:
        # 结构: 21 FF 0B "NETSCAPE2.0" 03 01 LL LL 00
        # 循环次数在 marker 之后 2 字节处，小端序
        loop_pos = idx + len(marker) + 2
        data[loop_pos] = loop_count & 0xFF
        data[loop_pos + 1] = (loop_count >> 8) & 0xFF
        with open(gif_path, "wb") as f:
            f.write(data)
    # 若无 Netscape 块，GIF 默认就只播一次，无需处理


if __name__ == "__main__":
    exit_to_entrance_gif(
        exit_gif_path="退出动画.gif",
        entrance_gif_path="入场动画.gif",
        play_once=True,
    )
    print("已生成只播放一次的入场动画.gif")