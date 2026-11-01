import os
import sys
import random
import traceback  # 新增：用于打印详细报错
from PIL import Image
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget, QVBoxLayout, QLineEdit
from PySide6.QtGui import QMovie, QAction, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QSize, QRect, QTimer, QUrl, QThread, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# ====== GIF 原始尺寸 & 显示尺寸 ======
GIF_W, GIF_H = 713, 400
DISP_W, DISP_H = 345, 200
SCALE_X = DISP_W / GIF_W
SCALE_Y = DISP_H / GIF_H
DRAG_THRESHOLD = 5


def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ====== 后台运行离线模型的线程 ======
class LLMThread(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        global llm

    def run(self):
        try:
            from llama_cpp import Llama
            global llm

            # 1. 如果模型还没加载，先加载模型
            if 'llm' not in globals() or llm is None:
                # 直接使用绝对路径，确保能找到文件
                model_path = r"E:\PYSIDE6\.venv\Lib\qwen2.5-3b-instruct-q4_k_m.gguf"

                # 如果 3B 跑起来太卡，你可以注释掉上面那行，换回下面这行 0.5B
                # model_path = r"E:\PYSIDE6\.venv\Lib\qwen2.5-0.5b-instruct-q5_k_m.gguf"

                # n_ctx=2048 表示上下文长度，n_threads=4 表示用4个CPU核心
                llm = Llama(model_path=model_path, n_ctx=2048, n_threads=4, verbose=False)

            # 2. 设置桌宠的人设
            system_prompt = "你是一个可爱的桌面宠物，性格傲娇但粘人。请用简短、口语化的一句话回复主人，不超过30个字。不要使用任何括号或动作描写。"

            # 3. 进行对话推理
            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": self.prompt}
                ],
                max_tokens=50,
                temperature=0.7
            )

            reply_text = response['choices'][0]['message']['content'].strip()
            self.finished.emit(reply_text)

        except Exception as e:
            # 把完整的错误打印到终端控制台
            traceback.print_exc()
            # 把错误简要显示在气泡里
            self.error.emit(f"{type(e).__name__}: {str(e)}")


class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.state = "enter"
        self.exiting = False
        self.pending_anger = False

        # 路径配置
        self.idle_gif = resource_path("待机动画.gif")
        self.click_left_gif = resource_path("点击左臂动画.gif")
        self.click_right_gif = resource_path("点击右臂动画.gif")
        self.leg_left_gif = resource_path("点击左腿动画.gif")
        self.leg_right_gif = resource_path("点击右腿动画.gif")
        self.body_gif = resource_path("点击身体动画.gif")
        self.drag_gif = resource_path("长按动画.gif")
        self.exit_gif = resource_path("退出动画.gif")
        self.enter_gif = resource_path("入场动画.gif")
        self.anger_gif = resource_path("愤怒动画.gif")
        self.anger_sound_path = resource_path("愤怒音效.mp4")

        self.movie = QMovie(self.enter_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.setMovie(self.movie)
        self.movie.frameChanged.connect(self.adjust_size)
        self.movie.finished.connect(self.on_movie_finished)

        self.enter_played_once = False
        self.enter_loop_timer = QTimer(self)
        self.enter_loop_timer.setSingleShot(True)
        self.enter_loop_timer.timeout.connect(self._on_enter_loop_end)

        self.movie.start()
        self.resize(DISP_W, DISP_H)
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

        self.dragging = False
        self.drag_mode = False
        self.moved = False
        self.offset = QPoint()
        self.press_pos = QPoint()

        # ====== 音效 ======
        self.body_sound_path = self._pick_body_sound()
        self.body_audio = QAudioOutput(self)
        self.body_audio.setVolume(1.0)
        self.body_player = QMediaPlayer(self)
        self.body_player.setAudioOutput(self.body_audio)
        self.body_player.setSource(QUrl.fromLocalFile(self.body_sound_path))

        self.anger_audio = QAudioOutput(self)
        self.anger_audio.setVolume(1.0)
        self.anger_player = QMediaPlayer(self)
        self.anger_player.setAudioOutput(self.anger_audio)
        self.anger_player.setSource(QUrl.fromLocalFile(self.anger_sound_path))

        # ====== 新增：UI 组件（聊天气泡与输入框） ======
        self.setup_chat_ui()

        # ====== 居中显示 ======
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.update_chat_ui_position()

    def setup_chat_ui(self):
        self.chat_bubble = QLabel("点我输入框，和我聊天吧~")
        self.chat_bubble.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.chat_bubble.setAttribute(Qt.WA_TranslucentBackground)
        self.chat_bubble.setStyleSheet("""
            background-color: rgba(30, 30, 30, 200); 
            color: white; 
            border-radius: 10px; 
            padding: 10px; 
            font-size: 14px;
        """)
        self.chat_bubble.setWordWrap(True)
        self.chat_bubble.setAlignment(Qt.AlignCenter)
        self.chat_bubble.resize(250, 80)
        self.chat_bubble.hide()

        self.input_box = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.input_box.setAttribute(Qt.WA_TranslucentBackground)
        layout = QVBoxLayout(self.input_box)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("按回车发送...")
        self.text_input.setStyleSheet("""
            background-color: rgba(255, 255, 255, 230);
            border: 2px solid #a0a0a0;
            border-radius: 15px;
            padding: 5px 10px;
            font-size: 14px;
        """)
        self.text_input.returnPressed.connect(self.send_message)
        layout.addWidget(self.text_input)
        self.input_box.resize(250, 35)
        self.input_box.hide()

    def update_chat_ui_position(self):
        pet_x, pet_y = self.x(), self.y()
        self.input_box.move(pet_x + 47, pet_y + DISP_H + 10)
        self.chat_bubble.move(pet_x + 47, pet_y - 90)

    def send_message(self):
        user_text = self.text_input.text().strip()
        if not user_text:
            return

        self.text_input.clear()
        self.chat_bubble.setText("3B模型思考中...请稍候")
        self.chat_bubble.show()
        self.update_chat_ui_position()

        # 启动后台线程
        self.llm_thread = LLMThread(user_text)
        self.llm_thread.finished.connect(self.on_llm_reply)
        self.llm_thread.error.connect(self.on_llm_error)
        self.llm_thread.start()

    def on_llm_reply(self, reply_text):
        self.chat_bubble.setText(reply_text)
        QTimer.singleShot(5000, self.chat_bubble.hide)

    def on_llm_error(self, err_msg):
        self.chat_bubble.setText(f"出错啦: {err_msg}")
        QTimer.singleShot(5000, self.chat_bubble.hide)

    def toggle_input_box(self):
        if self.input_box.isVisible():
            self.input_box.hide()
        else:
            self.update_chat_ui_position()
            self.input_box.show()
            self.text_input.setFocus()

    @staticmethod
    def _pick_body_sound():
        for name in ("点击身体叫声.wav", "点击身体叫声.mp3", "点击身体叫声.MP4", "点击身体叫声.mp4"):
            if os.path.exists(resource_path(name)):
                return resource_path(name)
        return resource_path("点击身体叫声.mp4")

    def adjust_size(self):
        self.resize(self.movie.currentPixmap().size())

    def _schedule_enter_timeout(self):
        total_ms = self._get_gif_duration_ms(self.enter_gif)
        if total_ms <= 0:
            n = self.movie.frameCount() or 60
            delay = self.movie.nextFrameDelay() or 100
            total_ms = n * (delay if delay > 0 else 100)
        self.enter_loop_timer.start(total_ms + 100)

    @staticmethod
    def _get_gif_duration_ms(gif_path):
        try:
            with Image.open(gif_path) as im:
                total = 0
                n = getattr(im, "n_frames", 1)
                for i in range(n):
                    im.seek(i)
                    total += im.info.get("duration", 100)
                return total
        except Exception:
            return 0

    def _on_enter_loop_end(self):
        if self.state != "enter" or self.enter_played_once:
            return
        self.enter_played_once = True
        self.play_gif(self.idle_gif, "idle")

    def play_gif(self, gif_path, new_state):
        if self.state == new_state and self.movie.fileName() == gif_path:
            return
        self.state = new_state
        self.movie.stop()
        self.movie.setFileName(gif_path)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.movie.start()

    def play_click(self, gif_path) -> bool:
        if self.state in ("enter", "click", "anger") or self.exiting:
            return False
        self.play_gif(gif_path, "click")
        return True

    def _play_body_sound(self):
        self.body_player.stop()
        self.body_player.setPosition(0)
        self.body_player.play()

    def play_anger(self):
        self.play_gif(self.anger_gif, "anger")
        self.anger_player.stop()
        self.anger_player.setPosition(0)
        self.anger_player.play()

    def start_drag_anim(self):
        if self.drag_mode or self.exiting or self.state in ("enter", "anger"):
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
        if self.state == "enter":
            if self.enter_played_once:
                return
            self.enter_played_once = True
            self.enter_loop_timer.stop()
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "click":
            if self.pending_anger:
                self.pending_anger = False
                self.play_anger()
            else:
                self.play_gif(self.idle_gif, "idle")
        elif self.state == "anger":
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "drag" and self.drag_mode:
            self.movie.stop()
            self.movie.start()
        elif self.state == "exit" and self.exiting:
            QApplication.quit()

    def mousePressEvent(self, event):
        if self.exiting or self.state in ("enter", "anger"):
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.press_pos = event.position().toPoint()
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.exiting or self.state in ("enter", "anger") or not self.dragging:
            return

        cur = event.position().toPoint()
        if not self.moved:
            if (cur - self.press_pos).manhattanLength() >= DRAG_THRESHOLD:
                self.moved = True
                self.start_drag_anim()

        if self.moved:
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)
            self.update_chat_ui_position()

    def mouseReleaseEvent(self, event):
        if self.exiting or self.state in ("enter", "anger"):
            return
        if event.button() == Qt.LeftButton:
            self.dragging = False

            if self.moved:
                self.stop_drag_anim()
            else:
                click_pos = event.position().toPoint()

                if self.body_rect.contains(click_pos):
                    if self.play_click(self.body_gif):
                        self._play_body_sound()
                        if random.random() < 0.30:
                            self.pending_anger = True
                        else:
                            self.pending_anger = False
                    self.toggle_input_box()

                elif self.left_arm_rect.contains(click_pos):
                    self.play_click(self.click_left_gif)
                elif self.right_arm_rect.contains(click_pos):
                    self.play_click(self.click_right_gif)
                elif self.left_leg_rect.contains(click_pos):
                    self.play_click(self.leg_left_gif)
                elif self.right_leg_rect.contains(click_pos):
                    self.play_click(self.leg_right_gif)

            self.moved = False

    def contextMenuEvent(self, event):
        if self.exiting or self.state in ("enter", "anger"):
            return
        menu = QMenu(self)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.start_exit_anim)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def closeEvent(self, event):
        self.chat_bubble.close()
        self.input_box.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())