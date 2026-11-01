import os
import sys
import random
import traceback
import requests
import json
from PIL import Image
from PySide6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidget, QVBoxLayout,
    QLineEdit, QTextEdit
)
from PySide6.QtGui import QMovie, QAction, QActionGroup, QGuiApplication, QTextCursor
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


def fast_search(query, timeout=3):
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        resp = requests.get(url, params=params, timeout=timeout)
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:2]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(topic["Text"])
        return "\n".join(results)
    except Exception:
        return ""


# ====== 后台运行模型的线程 ======
class LLMThread(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, prompt, history_messages, model_size):
        super().__init__()
        self.prompt = prompt
        self.history_messages = history_messages
        self.model_size = model_size
        global llm

    def run(self):
        try:
            if self.model_size == "联网":
                search_result_text = fast_search(self.prompt)
                system_prompt = (
                    "你现在是《我的世界》的史蒂夫，性格硬汉、傲娇。"
                    "请用简短、口语化的一句话回复玩家，不超过60字。不要使用括号描写。"
                )
                if search_result_text:
                    system_prompt += f"\n【以下是联网查到的资料，请结合它回答】\n{search_result_text}"

                messages = [{"role": "system", "content": system_prompt}]
                for msg in self.history_messages:
                    messages.append(msg)
                messages.append({"role": "user", "content": self.prompt})

                url = "https://text.pollinations.ai/openai"
                payload = {
                    "messages": messages,
                    "model": "openai-fast",
                    "temperature": 0.7,
                    "stream": True
                }

                try:
                    resp = requests.post(url, json=payload, stream=True, timeout=(5, 15))
                    if resp.status_code == 200:
                        full_reply = ""
                        for line in resp.iter_lines():
                            if line:
                                line_text = line.decode('utf-8').strip()
                                if line_text.startswith("data: "):
                                    data_str = line_text[6:]
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        data_json = json.loads(data_str)
                                        choices = data_json.get("choices")
                                        if choices:
                                            delta = choices[0].get("delta", {})
                                            if "content" in delta and delta["content"]:
                                                full_reply += delta["content"]
                                    except json.JSONDecodeError:
                                        pass
                        self.finished.emit(full_reply)
                        return
                    else:
                        self.error.emit(f"联网接口错误: {resp.status_code}")
                        return
                except requests.exceptions.Timeout:
                    self.error.emit("网络请求超时，请检查联网状态！")
                    return

            # 本地离线模式
            from llama_cpp import Llama
            global llm

            if self.model_size == "0.5B":
                model_path = r"E:\PYSIDE6\.venv\Lib\qwen2.5-0.5b-instruct-q5_k_m.gguf"
            else:
                model_path = r"E:\PYSIDE6\.venv\Lib\qwen2.5-3b-instruct-q4_k_m.gguf"

            if 'llm' not in globals() or llm is None or getattr(llm, 'model_path', '') != model_path:
                llm = None
                import gc
                gc.collect()
                llm = Llama(model_path=model_path, n_ctx=1024, n_threads=4, n_batch=128, use_mmap=True, verbose=False)
                llm.model_path = model_path

            system_prompt = (
                "你现在是《我的世界》(Minecraft) 里的史蒂夫(Steve)。"
                "你是一个沉默寡言、工作狂的方块人，三句话离不开挖矿、打怪（苦力怕、僵尸）、砍树和造房子。"
                "请用简短、口语化的一句话回复玩家，绝对不要超过60个字。不要使用任何动作括号描写。"
            )

            messages = [{"role": "system", "content": system_prompt}]
            for msg in self.history_messages:
                messages.append(msg)
            messages.append({"role": "user", "content": self.prompt})

            stream = llm.create_chat_completion(
                messages=messages, max_tokens=80, temperature=0.75, stream=True
            )

            full_reply = ""
            for chunk in stream:
                delta = chunk['choices'][0]['delta']
                if 'content' in delta:
                    full_reply += delta['content']

            self.finished.emit(full_reply)

        except Exception as e:
            traceback.print_exc()
            self.error.emit(f"出错: {str(e)}")


class DesktopPet(QLabel):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.state = "enter"
        self.exiting = False
        self.pending_anger = False
        self.chat_history = []
        self.ai_model_ready = False
        self.current_model = "0.5B"

        self.pending_reply = ""
        self.thinking_finished = False

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

        self.thinking_gif = resource_path("思考动画.gif")
        self.answer_gif = resource_path("回答动画.gif")

        self.movie = QMovie(self.enter_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.setMovie(self.movie)
        self.movie.frameChanged.connect(self.adjust_size)
        self.movie.finished.connect(self.on_movie_finished)

        self.enter_played_once = False
        self.enter_loop_timer = QTimer(self)
        self.enter_loop_timer.setSingleShot(True)
        self.enter_loop_timer.timeout.connect(self._on_enter_loop_end)

        # ====== 【新增】随机动作单次播放定时器 ======
        self.random_anim_timer = QTimer(self)
        self.random_anim_timer.setSingleShot(True)
        self.random_anim_timer.timeout.connect(self._on_random_anim_end)
        # =========================================

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

        self.setup_chat_ui()

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.update_chat_ui_position()

    def setup_chat_ui(self):
        # 回话框 (历史记录)
        self.history_box = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.history_box.setAttribute(Qt.WA_TranslucentBackground)
        hist_layout = QVBoxLayout(self.history_box)
        hist_layout.setContentsMargins(0, 0, 0, 0)

        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        self.history_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.history_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history_text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(255, 255, 255, 240); 
                border-radius: 10px; 
                padding: 10px; 
                font-size: 14px;
                color: #333;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0, 0, 0, 20);
                width: 8px;
                margin: 0px 0px 0px 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 0, 0, 60);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)
        hist_layout.addWidget(self.history_text)
        self.history_box.resize(300, 250)
        self.history_box.hide()

        # 提示气泡
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

        # 对话框 (输入框)
        self.input_box = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.input_box.setAttribute(Qt.WA_TranslucentBackground)
        main_layout = QVBoxLayout(self.input_box)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("右键选择模型后聊天...")
        self.text_input.setStyleSheet("""
            background-color: rgba(255, 255, 255, 230);
            border: 2px solid #a0a0a0;
            border-radius: 15px;
            padding: 5px 10px;
            font-size: 14px;
        """)
        self.text_input.returnPressed.connect(self.send_message)
        self.text_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text_input.customContextMenuRequested.connect(self.show_input_context_menu)

        main_layout.addWidget(self.text_input)
        self.input_box.resize(300, 35)
        self.input_box.hide()

    def show_input_context_menu(self, pos):
        menu = QMenu(self.text_input)

        dialog_menu = menu.addMenu("📜 对话框")
        show_dialog = QAction("显示", self)
        hide_dialog = QAction("隐藏", self)
        show_dialog.triggered.connect(self._menu_show_input)
        hide_dialog.triggered.connect(self._menu_hide_input)
        dialog_menu.addAction(show_dialog)
        dialog_menu.addAction(hide_dialog)

        hist_menu = menu.addMenu("📜 回话框")
        show_hist = QAction("显示", self)
        hide_hist = QAction("隐藏", self)
        show_hist.triggered.connect(self._menu_show_hist)
        hide_hist.triggered.connect(self._menu_hide_hist)
        hist_menu.addAction(show_hist)
        hist_menu.addAction(hide_hist)

        menu.exec(self.text_input.mapToGlobal(pos))

    def update_chat_ui_position(self):
        pet_x, pet_y = self.x(), self.y()
        self.input_box.move(pet_x + 22, pet_y + DISP_H + 10)
        self.chat_bubble.move(pet_x + 47, pet_y - 90)
        self.history_box.move(pet_x + 22, pet_y - 260)

    def send_message(self):
        user_text = self.text_input.text().strip()
        if not user_text:
            return
        if not self.ai_model_ready:
            self.chat_bubble.setText("请先右键选择大脑！")
            self.chat_bubble.show()
            QTimer.singleShot(3000, self.chat_bubble.hide)
            return

        self.text_input.clear()

        self.history_text.append(f"<b>你：</b> {user_text}<br>")
        self.history_text.append("<b>史蒂夫：</b> ")

        self.pending_reply = ""
        self.thinking_finished = False

        self.state = "thinking"
        self.movie.stop()
        self.movie.setFileName(self.thinking_gif)
        self.movie.setScaledSize(QSize(DISP_W, DISP_H))
        self.movie.start()

        self.llm_thread = LLMThread(user_text, self.chat_history, self.current_model)
        self.llm_thread.finished.connect(self.on_llm_reply)
        self.llm_thread.error.connect(self.on_llm_error)
        self.llm_thread.start()

    def on_llm_reply(self, reply_text):
        self.pending_reply = reply_text
        if self.thinking_finished:
            self.execute_print_and_answer()

    def execute_print_and_answer(self):
        if not self.pending_reply:
            return

        cursor = self.history_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(self.pending_reply)
        self.history_text.setTextCursor(cursor)
        self.history_text.ensureCursorVisible()
        self.history_text.append("<br><br>")
        self.history_text.ensureCursorVisible()

        self.chat_history.append({"role": "user", "content": self.llm_thread.prompt})
        self.chat_history.append({"role": "assistant", "content": self.pending_reply})
        if len(self.chat_history) > 10:
            self.chat_history = self.chat_history[-10:]

        self.pending_reply = ""
        self.play_gif(self.answer_gif, "answer")

    def on_llm_error(self, err_msg):
        self.chat_bubble.setText(f"出错啦: {err_msg}")
        self.chat_bubble.show()
        QTimer.singleShot(5000, self.chat_bubble.hide)
        self.play_gif(self.idle_gif, "idle")

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
        if self.state in ("enter", "click", "anger", "thinking") or self.exiting:
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
        if self.drag_mode or self.exiting or self.state in ("enter", "anger", "thinking"):
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
        elif self.state == "answer":
            self.play_gif(self.idle_gif, "idle")
        elif self.state == "thinking":
            self.thinking_finished = True
            if self.pending_reply:
                self.execute_print_and_answer()
        elif self.state == "drag" and self.drag_mode:
            self.movie.stop()
            self.movie.start()
        elif self.state == "exit" and self.exiting:
            QApplication.quit()

    def mousePressEvent(self, event):
        if self.exiting or self.state in ("enter", "anger", "thinking"):
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.moved = False
            self.press_pos = event.position().toPoint()
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.exiting or self.state in ("enter", "anger", "thinking") or not self.dragging:
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
        if self.exiting or self.state in ("enter", "anger", "thinking"):
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
                        if random.random() < 0.25:
                            self.pending_anger = True
                        else:
                            self.pending_anger = False

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
        if self.exiting or self.state in ("enter", "anger", "thinking"):
            return

        menu = QMenu(self)

        # 1. AI 模型
        ai_menu = menu.addMenu("🧠 切换 AI 模型")
        action_group = QActionGroup(self)
        action_group.setExclusive(True)

        action_05 = QAction("离线简单0.5G内存AI模型", self, checkable=True)
        action_3b = QAction("离线复杂2.1GB内存AI模型", self, checkable=True)
        action_online = QAction("🌐 联网智能模式（免注册）", self, checkable=True)

        if self.current_model == "0.5B":
            action_05.setChecked(True)
        elif self.current_model == "3B":
            action_3b.setChecked(True)
        else:
            action_online.setChecked(True)

        action_group.addAction(action_05)
        action_group.addAction(action_3b)
        action_group.addAction(action_online)

        action_05.triggered.connect(lambda: self.change_model("0.5B"))
        action_3b.triggered.connect(lambda: self.change_model("3B"))
        action_online.triggered.connect(lambda: self.change_model("联网"))

        ai_menu.addAction(action_05)
        ai_menu.addAction(action_3b)
        ai_menu.addAction(action_online)

        # 2. 对话框
        dialog_menu = menu.addMenu("📜 对话框")
        show_dialog = QAction("显示", self)
        hide_dialog = QAction("隐藏", self)
        show_dialog.triggered.connect(self._menu_show_input)
        hide_dialog.triggered.connect(self._menu_hide_input)
        dialog_menu.addAction(show_dialog)
        dialog_menu.addAction(hide_dialog)

        # 3. 回话框
        hist_menu = menu.addMenu("📜 回话框")
        show_hist = QAction("显示", self)
        hide_hist = QAction("隐藏", self)
        show_hist.triggered.connect(self._menu_show_hist)
        hide_hist.triggered.connect(self._menu_hide_hist)
        hist_menu.addAction(show_hist)
        hist_menu.addAction(hide_hist)

        # 4. 随机动作
        random_action = QAction("🎲 随机动作", self)
        random_action.triggered.connect(self.play_random_anim)
        menu.addAction(random_action)

        menu.addSeparator()

        # 5. 退出
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.start_exit_anim)
        menu.addAction(quit_action)
        menu.exec(event.globalPos())

    def play_random_anim(self):
        """随机执行一个逻辑关联的动画（只播放一次）"""
        if self.state in ("enter", "anger", "thinking", "answer") or self.exiting:
            return

        actions = [
            (self.body_gif, "click", True, True),
            (self.click_left_gif, "click", False, False),
            (self.click_right_gif, "click", False, False),
            (self.leg_left_gif, "click", False, False),
            (self.leg_right_gif, "click", False, False),
            (self.drag_gif, "drag", False, False),
            (self.thinking_gif, "thinking", False, False),
            (self.answer_gif, "answer", False, False),
            (self.anger_gif, "anger", False, False)
        ]

        gif_path, new_state, play_sound, trigger_anger = random.choice(actions)

        if new_state == "anger":
            self.play_anger()
            self._force_stop_random_anim(gif_path)
            return

        if new_state == "drag":
            if self.drag_mode: return
            self.drag_mode = True
            self.play_gif(gif_path, "drag")
            self._force_stop_random_anim(gif_path)
            return

        if self.play_click(gif_path):
            if play_sound:
                self._play_body_sound()

            if trigger_anger:
                if random.random() < 0.25:
                    self.pending_anger = True
                else:
                    self.pending_anger = False
            self._force_stop_random_anim(gif_path)

    def _force_stop_random_anim(self, gif_path):
        """利用定时器强制截断无限循环的 GIF"""
        total_ms = self._get_gif_duration_ms(gif_path)
        if total_ms <= 0:
            total_ms = 1000
        # 停止原本可能存在的定时器
        self.random_anim_timer.stop()
        self.random_anim_timer.start(total_ms)

    def _on_random_anim_end(self):
        """定时器触发，强制终止并回到待机"""
        if self.exiting:
            return

        # 如果是长按状态，解除长按
        if self.drag_mode:
            self.drag_mode = False

        # 切回待机
        self.play_gif(self.idle_gif, "idle")

    def _menu_show_input(self):
        self.update_chat_ui_position()
        self.input_box.show()

    def _menu_hide_input(self):
        self.input_box.hide()

    def _menu_show_hist(self):
        self.update_chat_ui_position()
        self.history_box.show()

    def _menu_hide_hist(self):
        self.history_box.hide()

    def change_model(self, model_size):
        self.current_model = model_size
        self.ai_model_ready = True
        self.chat_history = []

        if model_size == "0.5B":
            model_name = "简单 (0.5B)"
        elif model_size == "3B":
            model_name = "复杂 (3B)"
        else:
            model_name = "联网智能"

        self.chat_bubble.setText(f"已成功唤醒：{model_name} 大脑！")
        self.chat_bubble.show()
        QTimer.singleShot(3000, self.chat_bubble.hide)

        self.text_input.setPlaceholderText(f"当前：{model_name}，请说话...")

    def closeEvent(self, event):
        self.chat_bubble.close()
        self.input_box.close()
        self.history_box.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())