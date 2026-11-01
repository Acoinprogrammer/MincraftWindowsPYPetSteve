import os
import sys
from PIL import Image
from PySide6.QtWidgets import QApplication, QLabel, QMenu
from PySide6.QtGui import QMovie, QAction, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QTimer, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# ====== GIF 原始尺寸 & 显示尺寸 ======
GIF_W, GIF_H = 713, 400
DISP_W, DISP_H = 345, 200

SCALE_X = DISP_W / GIF_W
SCALE_Y = DISP_H / GIF_H

# 移动超过多少像素才算"拖动"（避免轻微手抖误触）
DRAG_THRESHOLD = 5

# ====== 解决打包后找不到资源文件的问题 ======
def resource_path(relative_path):
    """获取资源的绝对路径，兼容开发环境和 PyInstaller 打包后的环境"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ====== 动画状态 ======
        self.state = "enter"
        self.exiting = False

        # 使用 resource_path 包装所有文件路径
        self.idle_gif = resource_path("待机动画.gif")
        self.click_left_gif = resource_path("点击左臂动画.gif")
        self.click_right_gif = resource_path("点击右臂动画.gif")
        self.leg_left_gif = resource_path("点击左腿动画.gif")
        self.leg_right_gif = resource_path("点击右腿动画.gif")
        self.body_gif = resource_path("点击身体动画.gif")
        self.drag_gif = resource_path("长按动画.gif")
        self.exit_gif = resource_path("退出动画.gif")
        self.enter_gif = resource_path("入场动画.gif")

        # 初始化时直接加载入场动画
        self.movie = QMovie(self.enter_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.setMovie(self.movie)

        self.movie.frameChanged.connect(self.adjust_size)
        self.movie.finished.connect(self.on_movie_finished)

        # ====== 入场动画循环 GIF 的兜底：确保只播一轮 ======
        self.enter_played_once = False
        self.enter_loop_timer = QTimer(self)
        self.enter_loop_timer.setSingleShot(True)
        self.enter_loop_timer.timeout.connect(self._on_enter_loop_end)

        self.movie.start()
        self.resize(DISP_W, DISP_H)

        # 按入场 GIF 的真实总时长定时，播完一轮就切待机
        self._schedule_enter_timeout()

        # ====== 点击区域 ======
        arm_left_left = min(250, 292, 252, 293)
        arm_left_right = max(250, 292, 252, 293)
        arm_top = min(111, 111, 251, 251)
        arm_bottom = max(111, 111, 251, 251)

        leg_left_left = min(326, 352, 325, 348) - 9
        leg_left_right = max(326, 352, 325, 348)
        leg_top = min(242, 242, 385, 385)
        leg_bottom = max(242, 242, 385, 385) + 10

        body_left = 314
        body_right = 394
        body_top = 118
        body_bottom = 228

        def to_disp(l, r, t, b):
            l = int(l * SCALE_X)
            r = int(r * SCALE_X)
            t = int(t * SCALE_Y)
            b = int(b * SCALE_Y)
            return QRect(l, t, r - l, b - t)

        self.left_arm_rect = to_disp(arm_left_left, arm_left_right, arm_top, arm_bottom)
        self.right_arm_rect = to_disp(GIF_W - arm_left_right, GIF_W - arm_left_left, arm_top, arm_bottom)
        self.left_leg_rect = to_disp(leg_left_left, leg_left_right, leg_top, leg_bottom)
        self.right_leg_rect = to_disp(GIF_W - leg_left_right, GIF_W - leg_left_left, leg_top, leg_bottom)
        self.body_rect = to_disp(body_left, body_right, body_top, body_bottom)

        # ====== 拖动相关 ======
        self.dragging = False
        self.drag_mode = False
        self.moved = False
        self.offset = QPoint()
        self.press_pos = QPoint()

        # ====== 点击身体音效 ======
        self.body_sound_path = self._pick_body_sound()
        self.body_audio = QAudioOutput(self)
        self.body_audio.setVolume(1.0)  # 0.0 ~ 1.0
        self.body_player = QMediaPlayer(self)
        self.body_player.setAudioOutput(self.body_audio)
        self.body_player.setSource(QUrl.fromLocalFile(self.body_sound_path))
        print(f"点击身体音效：{self.body_sound_path}")

        # ====== 新增：强制窗口居中显示，防止打包后窗口飞出屏幕 ======
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    @staticmethod
    def _pick_body_sound():
        """优先找 wav / mp3，找不到再退回 MP4。"""
        for name in ("点击身体叫声.wav", "点击身体叫声.mp3", "点击身体叫声.MP4", "点击身体叫声.mp4"):
            if os.path.exists(resource_path(name)):
                return resource_path(name)
        # 都不存在也返回 MP4，让 Qt 自己报找不到文件
        return resource_path("点击身体叫声.mp4")

    def adjust_size(self):
        self.resize(self.movie.currentPixmap().size())

    # ---------- 入场循环 GIF 兜底 ----------
    def _schedule_enter_timeout(self):
        """用 PIL 读取入场 GIF 的真实总时长，到点切待机。"""
        total_ms = self._get_gif_duration_ms(self.enter_gif)
        if total_ms <= 0:
            # 读不到就退回 QMovie 估算
            n = self.movie.frameCount()
            if n <= 0:
                n = 60
            delay = self.movie.nextFrameDelay() or 100
            if delay <= 0:
                delay = 100
            total_ms = n * delay
        print(f"入场动画总时长：{total_ms} ms")
        # 留一点余量，确保最后一帧播完
        self.enter_loop_timer.start(total_ms + 100)

    @staticmethod
    def _get_gif_duration_ms(gif_path):
        """用 PIL 精确计算 GIF 一轮播放的总时长（毫秒）。"""
        try:
            with Image.open(gif_path) as im:
                total = 0
                n = getattr(im, "n_frames", 1)
                for i in range(n):
                    im.seek(i)
                    # duration 单位是毫秒，缺失时按 100ms（GIF 默认）算
                    total += im.info.get("duration", 100)
                return total
        except Exception as e:
            print(f"读取 GIF 时长失败：{e}")
            return 0

    def _on_enter_loop_end(self):
        """入场动画播完一轮：循环 GIF 靠这里兜底切待机。"""
        if self.state != "enter":
            return
        if self.enter_played_once:
            return
        self.enter_played_once = True
        print("入场动画播放完毕（兜底），进入待机。")
        self.play_gif(self.idle_gif, "idle")

    # ---------- 动画切换 ----------
    def play_gif(self, gif_path, new_state):
        # 防止重复加载同一个动画导致鬼畜
        if self.state == new_state and self.movie.fileName() == gif_path:
            return

        self.state = new_state
        self.movie.stop()
        self.movie.setFileName(gif_path)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.movie.start()

    def play_click(self, gif_path) -> bool:
        """
        播放点击动画。
        返回 True 表示动画真的被重新触发了；False 表示被忽略（已在播放中/入场中/退出中）。
        """
        if self.state in ("enter", "click") or self.exiting:
            return False
        self.play_gif(gif_path, "click")
        return True

    def _play_body_sound(self):
        """播放点击身体音效。"""
        # 回到开头再播，避免连续点击时没声音
        self.body_player.stop()
        self.body_player.setPosition(0)
        self.body_player.play()

    def start_drag_anim(self):
        if self.drag_mode or self.exiting or self.state == "enter":
            return
        self.drag_mode = True
        self.play_gif(self.drag_gif, "drag")

    def stop_drag_anim(self):
        if not self.drag_mode:
            return
        self.drag_mode = False
        self.play_gif(self.idle_gif, "idle")

    def start_exit_anim(self):
        if self.exiting:
            return
        self.exiting = True
        self.dragging = False
        self.drag_mode = False
        self.play_gif(self.exit_gif, "exit")

    def on_movie_finished(self):
        """GIF 播完（仅非循环 GIF 会触发）"""
        if self.state == "enter":
            if self.enter_played_once:
                return
            self.enter_played_once = True
            self.enter_loop_timer.stop()
            print("入场动画播放完毕，进入待机。")
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "click":
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "drag" and self.drag_mode:
            self.movie.stop()
            self.movie.start()
        elif self.state == "exit" and self.exiting:
            print("退出动画播放完毕，程序退出。")
            QApplication.quit()

    # ---------- 鼠标事件 ----------
    def mousePressEvent(self, event):
        if self.exiting or self.state == "enter":
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.press_pos = event.position().toPoint()
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.exiting or self.state == "enter" or not self.dragging:
            return

        cur = event.position().toPoint()
        if not self.moved:
            if (cur - self.press_pos).manhattanLength() >= DRAG_THRESHOLD:
                self.moved = True
                self.start_drag_anim()

        if self.moved:
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if self.exiting or self.state == "enter":
            return
        if event.button() == Qt.LeftButton:
            self.dragging = False

            if self.moved:
                self.stop_drag_anim()
            else:
                click_pos = event.position().toPoint()

                if self.body_rect.contains(click_pos):
                    print("  -> 点中身体 ✅")
                    # 只有动画真的重新播放了，才出声，保证"一次叫声对应一次动画"
                    if self.play_click(self.body_gif):
                        self._play_body_sound()
                    else:
                        print("     （身体动画播放中，忽略本次点击）")
                elif self.left_arm_rect.contains(click_pos):
                    print("  -> 点中左臂 ✅")
                    self.play_click(self.click_left_gif)
                elif self.right_arm_rect.contains(click_pos):
                    print("  -> 点中右臂 ✅")
                    self.play_click(self.click_right_gif)
                elif self.left_leg_rect.contains(click_pos):
                    print("  -> 点中左腿 ✅")
                    self.play_click(self.leg_left_gif)
                elif self.right_leg_rect.contains(click_pos):
                    print("  -> 点中右腿 ✅")
                    self.play_click(self.leg_right_gif)
                else:
                    print("  -> 点到别处 ❌")

            self.moved = False

    def contextMenuEvent(self, event):
        if self.exiting or self.state == "enter":
            return

        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.start_exit_anim)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    print("程序开始启动...")
    pet = DesktopPet()
    pet.show()
    print("窗口已显示，进入事件循环。")
    sys.exit(app.exec())