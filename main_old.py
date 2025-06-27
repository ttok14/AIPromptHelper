import sys
import os
import datetime
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QFileDialog, QPlainTextEdit, QListWidget, QMessageBox
)
from PySide6.QtCore import QThread, QObject, Signal, Qt

# Gemini 라이브러리 임포트
import google.generativeai as genai

# --- 백그라운드 작업을 위한 Worker 클래스 ---import sys
import os
import datetime
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QFileDialog, QPlainTextEdit, QListWidget, QMessageBox, QSplitter
)
from PySide6.QtCore import QThread, QObject, Signal, Qt

# Gemini 라이브러리 임포트
import google.generativeai as genai

# --- 백그라운드 작업을 위한 Worker 클래스 ---
class GeminiWorker(QObject):
    log_message = Signal(str)
    progress_update = Signal(int, int) # (현재 파일 번호, 전체 파일 수)
    task_finished = Signal(object) # 완료 시 업데이트된 history 전달
    initialization_finished = Signal(object, str) # 세션 초기화 완료 시 (history, session_path) 전달

    def __init__(self, api_key, model_name):
        super().__init__()
        self.api_key = api_key
        self.model_name = model_name
        self.is_running = True

    def initialize_session(self, initial_prompt, session_path):
        """새로운 세션을 시작하고 사용자 정의 초기 컨텍스트를 주입합니다."""
        try:
            self.log_message.emit("API 키 설정 및 모델 초기화 중...")
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            chat_session = model.start_chat(history=[])

            self.log_message.emit("Gemini에게 초기 설정 프롬프트를 전송합니다...")
            response = chat_session.send_message(initial_prompt)
            
            self.log_message.emit(f"세션 초기화 완료. 응답: '{response.text[:80].replace(os.linesep, ' ')}...'")
            self.log_message.emit(f"초기화 토큰 사용량: {response.usage_metadata}")
            self.log_message.emit("-" * 40)
            
            self.initialization_finished.emit(chat_session.history, session_path)

        except Exception as e:
            self.log_message.emit(f"[오류] 세션 초기화 실패: {e}")
            self.task_finished.emit(None)

    def process_files(self, history, iterative_prompt, content_files, output_dir, filename_pattern):
        """기존 세션을 기반으로 파일들을 반복 처리합니다."""
        try:
            self.log_message.emit("기존 세션 정보를 바탕으로 모델을 설정합니다...")
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            chat_session = model.start_chat(history=history)
            self.log_message.emit("세션 복원 완료.")

        except Exception as e:
            self.log_message.emit(f"[오류] 세션 복원 실패: {e}")
            self.task_finished.emit(history)
            return
        
        total_files = len(content_files)
        for i, file_path_str in enumerate(content_files):
            if not self.is_running:
                self.log_message.emit("사용자에 의해 작업이 중단되었습니다.")
                break
            
            self.progress_update.emit(i + 1, total_files)
            
            try:
                p = Path(file_path_str)
                self.log_message.emit(f"'{p.name}' 파일 처리 시작...")
                content = p.read_text(encoding='utf-8')
                
                # 플레이스홀더 치환
                prompt_to_send = iterative_prompt.replace("{INPUT_FILE_CONTENT}", content)
                prompt_to_send = prompt_to_send.replace("{INPUT_FILE_NAME}", p.name)
                prompt_to_send = prompt_to_send.replace("{INPUT_FILE_NAME_NO_EXT}", p.stem)

                response = chat_session.send_message(prompt_to_send)
                
                # 출력 파일명 생성 (플레이스홀더 치환)
                output_filename = filename_pattern.replace("{INPUT_FILE_NAME}", p.name)
                output_filename = output_filename.replace("{INPUT_FILE_NAME_NO_EXT}", p.stem)
                
                output_path = Path(output_dir) / output_filename
                output_path.write_text(response.text, encoding='utf-8')
                
                self.log_message.emit(f"✅ 성공: '{output_filename}' 저장 완료.")
                self.log_message.emit(f"   토큰 사용량: {response.usage_metadata}")

            except Exception as e:
                self.log_message.emit(f"❌ 오류: '{Path(file_path_str).name}' 처리 중 문제 발생: {e}")
            
            self.log_message.emit("-" * 40)
        
        self.log_message.emit("모든 작업이 완료되었습니다.")
        self.task_finished.emit(chat_session.history)

    def stop(self):
        self.is_running = False

# --- 메인 윈도우 클래스 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini Batch Processor v0.3.0")
        self.setGeometry(100, 100, 1200, 800)

        self.worker = None
        self.thread = None
        self.session_history = []
        self.current_session_path = None

        self.init_ui()
        self.update_ui_state()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # 스플리터로 좌우 영역 나누기
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- 좌측 패널: 설정 ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        splitter.addWidget(left_panel)
        
        # 1. 기본 설정
        settings_group = QGroupBox("1. API & 모델 설정")
        settings_layout = QGridLayout(settings_group)
        settings_layout.addWidget(QLabel("Google API Key:"), 0, 0)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        settings_layout.addWidget(self.api_key_edit, 0, 1)
        settings_layout.addWidget(QLabel("Gemini 모델:"), 1, 0)
        self.model_name_edit = QLineEdit("gemini-1.5-pro-latest")
        settings_layout.addWidget(self.model_name_edit, 1, 1)
        left_layout.addWidget(settings_group)
        
        # 2. 프롬프트 템플릿
        prompt_group = QGroupBox("2. 프롬프트 템플릿")
        prompt_layout = QVBoxLayout(prompt_group)
        
        prompt_btn_layout = QHBoxLayout()
        btn_save_preset = QPushButton("프리셋 저장")
        btn_save_preset.clicked.connect(self.save_preset)
        btn_load_preset = QPushButton("프리셋 불러오기")
        btn_load_preset.clicked.connect(self.load_preset)
        prompt_btn_layout.addWidget(btn_save_preset)
        prompt_btn_layout.addWidget(btn_load_preset)
        prompt_layout.addLayout(prompt_btn_layout)

        prompt_layout.addWidget(QLabel("초기 설정 프롬프트 (AI 역할, 규칙 등)"))
        self.initial_prompt_edit = QPlainTextEdit()
        self.initial_prompt_edit.setPlaceholderText("예: 당신은 전문 번역가입니다. 다음 규칙을 따르세요...")
        prompt_layout.addWidget(self.initial_prompt_edit)
        
        prompt_layout.addWidget(QLabel("반복 처리 프롬프트 (플레이스홀더 사용)"))
        self.iterative_prompt_edit = QPlainTextEdit()
        self.iterative_prompt_edit.setPlaceholderText("예: 다음 내용을 번역해줘.\n---\n{INPUT_FILE_CONTENT}")
        prompt_layout.addWidget(self.iterative_prompt_edit)
        left_layout.addWidget(prompt_group)
        left_panel.setMinimumWidth(400)

        # --- 우측 패널: 실행 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        splitter.addWidget(right_panel)

        # 3. 세션 관리
        self.session_group = QGroupBox("3. 대화 기록 (세션)")
        session_layout = QGridLayout(self.session_group)
        self.btn_new_session = QPushButton("새 세션 시작")
        self.btn_new_session.clicked.connect(self.start_new_session)
        self.btn_load_session = QPushButton("기존 세션 불러오기")
        self.btn_load_session.clicked.connect(self.load_existing_session)
        session_layout.addWidget(self.btn_new_session, 0, 0)
        session_layout.addWidget(self.btn_load_session, 0, 1)
        session_layout.addWidget(QLabel("현재 세션 파일:"), 1, 0)
        self.session_status_label = QLabel("없음")
        self.session_status_label.setStyleSheet("font-weight: bold;")
        session_layout.addWidget(self.session_status_label, 1, 1)
        right_layout.addWidget(self.session_group)

        # 4. 입력 및 출력
        self.io_group = QGroupBox("4. 입력 파일 및 출력 설정")
        io_layout = QVBoxLayout(self.io_group)
        io_layout.addWidget(QLabel("입력 파일 목록"))
        self.file_list_widget = QListWidget()
        io_layout.addWidget(self.file_list_widget)
        
        file_btn_layout = QHBoxLayout()
        btn_add_files = QPushButton("파일 추가")
        btn_add_files.clicked.connect(self.add_files)
        btn_clear_list = QPushButton("목록 지우기")
        btn_clear_list.clicked.connect(self.file_list_widget.clear)
        file_btn_layout.addWidget(btn_add_files)
        file_btn_layout.addWidget(btn_clear_list)
        io_layout.addLayout(file_btn_layout)

        io_layout.addWidget(QLabel("출력 파일명 패턴:"))
        self.filename_pattern_edit = QLineEdit("{INPUT_FILE_NAME_NO_EXT}_result.txt")
        io_layout.addWidget(self.filename_pattern_edit)
        right_layout.addWidget(self.io_group)
        
        # 5. 실행 및 로그
        self.run_group = QGroupBox("5. 실행 및 로그")
        run_layout = QVBoxLayout(self.run_group)
        
        self.progress_label = QLabel("대기 중")
        run_layout.addWidget(self.progress_label)
        
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        run_layout.addWidget(self.log_widget)
        
        run_btn_layout = QHBoxLayout()
        self.start_button = QPushButton("✅ 생성 시작")
        self.start_button.setStyleSheet("font-size: 16px; padding: 10px; color: green;")
        self.start_button.clicked.connect(self.start_generation)
        self.cancel_button = QPushButton("❌ 작업 취소")
        self.cancel_button.setStyleSheet("font-size: 16px; padding: 10px; color: red;")
        self.cancel_button.clicked.connect(self.cancel_generation)
        run_btn_layout.addWidget(self.start_button)
        run_btn_layout.addWidget(self.cancel_button)
        run_layout.addLayout(run_btn_layout)
        right_layout.addWidget(self.run_group)
        
        splitter.setSizes([500, 700])
    
    # --- 상태 관리 ---
    def update_ui_state(self, processing=False):
        session_active = bool(self.session_history)
        
        # 처리 중일 때의 상태 관리
        if processing:
            self.start_button.hide()
            self.cancel_button.show()
            for widget in [self.session_group, self.io_group]:
                widget.setEnabled(False)
        else:
            self.start_button.show()
            self.cancel_button.hide()
            self.progress_label.setText("대기 중")
            for widget in [self.session_group, self.io_group]:
                widget.setEnabled(session_active)
        
        # 세션 활성화 여부에 따른 상태 관리
        self.btn_new_session.setEnabled(not processing)
        self.btn_load_session.setEnabled(not processing)
        if session_active:
             self.session_status_label.setText(Path(self.current_session_path).name)
        else:
             self.session_status_label.setText("없음")
             
    # --- 슬롯 함수 (이벤트 핸들러) ---
    def save_preset(self):
        preset_path, _ = QFileDialog.getSaveFileName(self, "프리셋 저장", "", "Preset Files (*.preset)")
        if not preset_path: return
        
        preset_data = {
            'initial_prompt': self.initial_prompt_edit.toPlainText(),
            'iterative_prompt': self.iterative_prompt_edit.toPlainText()
        }
        try:
            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(preset_data, f, ensure_ascii=False, indent=4)
            self.log(f"프리셋 '{Path(preset_path).name}'을 저장했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"프리셋 저장 중 오류 발생: {e}")

    def load_preset(self):
        preset_path, _ = QFileDialog.getOpenFileName(self, "프리셋 불러오기", "", "Preset Files (*.preset)")
        if not preset_path: return
        
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
            self.initial_prompt_edit.setPlainText(preset_data.get('initial_prompt', ''))
            self.iterative_prompt_edit.setPlainText(preset_data.get('iterative_prompt', ''))
            self.log(f"프리셋 '{Path(preset_path).name}'을 불러왔습니다.")
        except Exception as e:
            QMessageBox.critical(self, "불러오기 오류", f"프리셋 불러오기 중 오류 발생: {e}")
            
    def start_new_session(self):
        if not all([self.api_key_edit.text(), self.model_name_edit.text(), self.initial_prompt_edit.toPlainText()]):
            QMessageBox.warning(self, "입력 오류", "API 키, 모델 이름, 초기 설정 프롬프트를 모두 입력해야 합니다.")
            return

        session_path, _ = QFileDialog.getSaveFileName(self, "새 세션 파일(.json) 저장 위치 선택", "", "JSON Files (*.json)")
        if not session_path: return
        
        self.log_widget.clear()
        self.update_ui_state(processing=True)
        
        self.thread = QThread()
        self.worker = GeminiWorker(self.api_key_edit.text(), self.model_name_edit.text())
        self.worker.moveToThread(self.thread)

        self.worker.log_message.connect(self.log)
        self.worker.initialization_finished.connect(self.on_session_initialized)
        self.thread.started.connect(lambda: self.worker.initialize_session(
            self.initial_prompt_edit.toPlainText(), session_path
        ))
        self.thread.start()

    def on_session_initialized(self, history, session_path):
        if history:
            self.session_history = history
            self.current_session_path = session_path
            self._save_session_to_file()
            self.log("새로운 세션이 성공적으로 생성되고 파일로 저장되었습니다.")
        
        self.clean_up_thread()
        self.update_ui_state(processing=False)

    def load_existing_session(self):
        session_path, _ = QFileDialog.getOpenFileName(self, "불러올 세션 파일(.json) 선택", "", "JSON Files (*.json)")
        if not session_path: return
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                self.session_history = json.load(f)
            self.current_session_path = session_path
            self.log_widget.clear()
            self.log(f"세션 '{Path(session_path).name}'을 성공적으로 불러왔습니다.")
            self.update_ui_state()
        except Exception as e:
            QMessageBox.critical(self, "세션 불러오기 실패", f"세션 파일을 불러오는 중 오류가 발생했습니다: {e}")
            self.session_history = []
            self.current_session_path = None
            self.update_ui_state()
            
    def start_generation(self):
        if self.file_list_widget.count() == 0:
            QMessageBox.warning(self, "입력 오류", "하나 이상의 입력 파일을 추가해주세요.")
            return
        if not self.iterative_prompt_edit.toPlainText():
            QMessageBox.warning(self, "입력 오류", "반복 처리 프롬프트가 비어있습니다.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "결과를 저장할 폴더 선택")
        if not output_dir: return
        
        self.update_ui_state(processing=True)
        content_files = [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())]
        
        self.thread = QThread()
        self.worker = GeminiWorker(self.api_key_edit.text(), self.model_name_edit.text())
        self.worker.moveToThread(self.thread)

        self.worker.log_message.connect(self.log)
        self.worker.progress_update.connect(self.update_progress)
        self.worker.task_finished.connect(self.on_task_finished)
        self.thread.started.connect(lambda: self.worker.process_files(
            self.session_history, self.iterative_prompt_edit.toPlainText(),
            content_files, output_dir, self.filename_pattern_edit.text()
        ))
        self.thread.start()
        
    def cancel_generation(self):
        if self.worker:
            self.log(">>> 작업 취소를 요청합니다...")
            self.worker.stop()
            self.cancel_button.setEnabled(False) # 중복 클릭 방지

    def on_task_finished(self, updated_history):
        if updated_history:
            self.session_history = updated_history
            self._save_session_to_file()
            self.log("작업 완료 후 업데이트된 세션을 파일에 저장했습니다.")
        
        self.clean_up_thread()
        self.update_ui_state(processing=False)
        self.cancel_button.setEnabled(True) # 다음 작업을 위해 다시 활성화

    def update_progress(self, current, total):
        self.progress_label.setText(f"처리 중... ({current} / {total})")
        
    # --- 유틸리티 함수 ---
    def _save_session_to_file(self):
        if not self.current_session_path or not self.session_history: return
        history_to_save = [
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in self.session_history
        ]
        try:
            with open(self.current_session_path, 'w', encoding='utf-8') as f:
                json.dump(history_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log(f"[오류] 세션 파일 저장 실패: {e}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "입력 파일 선택", "", "모든 파일 (*.*)")
        if files:
            self.file_list_widget.addItems(files)

    def log(self, message):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_widget.appendPlainText(f"[{now}] {message}")
        self.log_widget.verticalScrollBar().setValue(self.log_widget.verticalScrollBar().maximum())

    def clean_up_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            self.thread.wait()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
class GeminiWorker(QObject):
    log_message = Signal(str)
    task_finished = Signal(object)
    initialization_finished = Signal(object, str)

    def __init__(self, api_key, model_name):
        super().__init__()
        self.api_key = api_key
        self.model_name = model_name
        self.is_running = True
        self.chat_session = None

    def initialize_session(self, rule_content, course_content, session_path):
        try:
            self.log_message.emit("API 키 설정 및 모델 초기화 중...")
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            self.chat_session = model.start_chat(history=[])

            initial_prompt = f"""
            당신은 '파이썬 교육용 프레젠테이션 프롬프트 전문 엔지니어'입니다.
            아래 제공되는 '전체 규칙'과 '전체 강의 목차'를 반드시 기억하고, 
            앞으로의 모든 요청을 이 기준에 따라 처리해야 합니다.

            ---[전체 규칙]---
            {rule_content}

            ---[전체 강의 목차]---
            {course_content}
            ---

            이 모든 내용을 완벽히 숙지했다면, "준비되었습니다. Rule.txt, Contents.txt, EntireCourse.txt 파일을 첨부해 주십시오." 라고만 응답하고 다음 입력을 기다리십시오.
            """
            
            self.log_message.emit("Gemini에게 기본 컨텍스트(규칙, 목차)를 전송하여 세션을 초기화합니다...")
            response = self.chat_session.send_message(initial_prompt)
            
            self.log_message.emit(f"세션 초기화 완료. 응답: '{response.text[:50]}...'")
            self.log_message.emit(f"초기화 토큰 사용량: {response.usage_metadata}")
            self.log_message.emit("-" * 40)
            
            self.initialization_finished.emit(self.chat_session.history, session_path)

        except Exception as e:
            self.log_message.emit(f"[오류] 세션 초기화 실패: {e}")
            self.task_finished.emit(None)

    def process_files(self, history, content_files, output_dir):
        try:
            self.log_message.emit("기존 세션 정보를 바탕으로 모델을 설정합니다...")
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model_name)
            # history는 이제 dict list이므로 바로 사용 가능
            self.chat_session = model.start_chat(history=history)
            self.log_message.emit("세션 복원 완료.")

        except Exception as e:
            self.log_message.emit(f"[오류] 세션 복원 실패: {e}")
            self.task_finished.emit(history)
            return

        for file_path in content_files:
            if not self.is_running:
                self.log_message.emit("작업이 중단되었습니다.")
                break
            
            try:
                self.log_message.emit(f"'{Path(file_path).name}' 파일 처리 시작...")
                content = Path(file_path).read_text(encoding='utf-8')
                
                prompt = f"""
                기억하고 있는 규칙과 목차를 기준으로, 아래 강의안의 프롬프트를 생성해줘.
                ---[강의안 내용]---
                {content}
                """
                
                response = self.chat_session.send_message(prompt)
                
                output_filename = f"{Path(file_path).stem}_prompt.txt"
                output_path = Path(output_dir) / output_filename
                output_path.write_text(response.text, encoding='utf-8')
                
                self.log_message.emit(f"✅ 성공: '{output_filename}' 저장 완료.")
                self.log_message.emit(f"   토큰 사용량: {response.usage_metadata}")

            except Exception as e:
                self.log_message.emit(f"❌ 오류: '{Path(file_path).name}' 처리 중 문제 발생: {e}")
            
            self.log_message.emit("-" * 40)
        
        self.log_message.emit("모든 작업이 완료되었습니다.")
        self.task_finished.emit(self.chat_session.history)

    def stop(self):
        self.is_running = False


# --- 메인 윈도우 클래스 ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini Prompt Automator v0.2.1 (Session-based, Bug Fixed)")
        self.setGeometry(100, 100, 800, 750)

        self.worker = None
        self.thread = None
        self.session_history = []
        self.current_session_path = None

        self.init_ui()
        self.update_ui_for_session_status()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 1. 설정 그룹 ---
        settings_group = QGroupBox("1. 기본 설정")
        settings_layout = QGridLayout(settings_group)
        
        settings_layout.addWidget(QLabel("Google API Key:"), 0, 0)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        settings_layout.addWidget(self.api_key_edit, 0, 1)
        
        settings_layout.addWidget(QLabel("Gemini 모델:"), 1, 0)
        self.model_name_edit = QLineEdit("gemini-1.5-pro-latest")
        settings_layout.addWidget(self.model_name_edit, 1, 1)

        main_layout.addWidget(settings_group)
        
        # --- 2. 세션 관리 그룹 ---
        session_group = QGroupBox("2. 세션 관리 (가장 먼저 시작)")
        session_layout = QGridLayout(session_group)

        self.btn_new_session = QPushButton("새 세션 시작")
        self.btn_new_session.clicked.connect(self.start_new_session)
        session_layout.addWidget(self.btn_new_session, 0, 0)

        self.btn_load_session = QPushButton("기존 세션 불러오기")
        self.btn_load_session.clicked.connect(self.load_existing_session)
        session_layout.addWidget(self.btn_load_session, 0, 1)

        session_layout.addWidget(QLabel("현재 세션:"), 1, 0)
        self.session_status_label = QLabel("없음")
        self.session_status_label.setStyleSheet("font-weight: bold;")
        session_layout.addWidget(self.session_status_label, 1, 1)

        main_layout.addWidget(session_group)

        # --- 3. 작업 파일 그룹 ---
        self.contents_group = QGroupBox("3. 작업할 강의안 파일 목록")
        contents_layout = QVBoxLayout(self.contents_group)

        self.file_list_widget = QListWidget()
        contents_layout.addWidget(self.file_list_widget)

        btn_layout = QHBoxLayout()
        self.btn_add_files = QPushButton("파일 추가")
        self.btn_add_files.clicked.connect(self.add_content_files)
        self.btn_clear_list = QPushButton("목록 지우기")
        self.btn_clear_list.clicked.connect(self.file_list_widget.clear)
        btn_layout.addWidget(self.btn_add_files)
        btn_layout.addWidget(self.btn_clear_list)
        contents_layout.addLayout(btn_layout)
        
        main_layout.addWidget(self.contents_group)

        # --- 4. 실행 및 로그 그룹 ---
        self.run_group = QGroupBox("4. 실행 및 로그")
        run_layout = QVBoxLayout(self.run_group)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        run_layout.addWidget(self.log_widget)
        
        self.start_button = QPushButton("프롬프트 생성 시작")
        self.start_button.setStyleSheet("font-size: 16px; padding: 10px;")
        self.start_button.clicked.connect(self.start_generation)
        run_layout.addWidget(self.start_button)
        
        main_layout.addWidget(self.run_group)
    
    # [BUG FIX] 함수 2개 수정
    def save_session_to_file(self):
        """현재 세션의 history를 JSON 파일로 저장"""
        if not self.current_session_path or not self.session_history:
            return

        # Gemini가 인식할 수 있는 정확한 dict 구조로 변환
        history_to_save = [
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in self.session_history
        ]
        
        try:
            with open(self.current_session_path, 'w', encoding='utf-8') as f:
                json.dump(history_to_save, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.log(f"[오류] 세션 파일 저장 실패: {e}")
            QMessageBox.warning(self, "저장 오류", f"세션 파일을 저장하는 데 실패했습니다: {e}")

    def load_existing_session(self):
        """기존 세션 파일을 불러오는 로직"""
        session_path, _ = QFileDialog.getOpenFileName(self, "불러올 세션 파일(.json) 선택", "", "JSON Files (*.json)")
        if not session_path:
            return
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            
            # JSON에서 읽은 dict 리스트를 그대로 history로 사용합니다.
            # 라이브러리가 이 형식을 직접 해석할 수 있습니다.
            self.session_history = history_data
            self.current_session_path = session_path
            self.log_widget.clear()
            self.log(f"세션 '{Path(session_path).name}'을 성공적으로 불러왔습니다.")
            self.update_ui_for_session_status()

        except Exception as e:
            QMessageBox.critical(self, "세션 불러오기 실패", f"세션 파일을 불러오는 중 오류가 발생했습니다: {e}")
            self.session_history = []
            self.current_session_path = None
            self.update_ui_for_session_status()
    # --- 수정 끝 ---
    
    def update_ui_for_session_status(self):
        session_active = bool(self.session_history)
        self.contents_group.setEnabled(session_active)
        self.run_group.setEnabled(session_active)
        if session_active:
             self.session_status_label.setText(Path(self.current_session_path).name)
        else:
             self.session_status_label.setText("없음")

    def start_new_session(self):
        api_key = self.api_key_edit.text()
        model_name = self.model_name_edit.text()
        if not all([api_key, model_name]):
            QMessageBox.warning(self, "입력 오류", "API 키와 모델 이름을 먼저 입력해주세요.")
            return

        rule_path, _ = QFileDialog.getOpenFileName(self, "1. 규칙(Rule.txt) 파일 선택", "", "Text Files (*.txt)")
        if not rule_path: return
        course_path, _ = QFileDialog.getOpenFileName(self, "2. 목차(EntireCourse.txt) 파일 선택", "", "Text Files (*.txt)")
        if not course_path: return

        session_path, _ = QFileDialog.getSaveFileName(self, "3. 새 세션 파일 저장 위치 선택", "", "JSON Files (*.json)")
        if not session_path: return
        
        try:
            rule_content = Path(rule_path).read_text(encoding='utf-8')
            course_content = Path(course_path).read_text(encoding='utf-8')
        except Exception as e:
            QMessageBox.critical(self, "파일 읽기 오류", f"규칙 또는 목차 파일을 읽는 데 실패했습니다: {e}")
            return
            
        self.log_widget.clear()
        self.set_ui_enabled(False)

        self.thread = QThread()
        self.worker = GeminiWorker(api_key, model_name)
        self.worker.moveToThread(self.thread)

        self.worker.log_message.connect(self.log)
        self.worker.initialization_finished.connect(self.on_session_initialized)
        self.thread.started.connect(lambda: self.worker.initialize_session(rule_content, course_content, session_path))
        
        self.thread.start()
    
    def on_session_initialized(self, history, session_path):
        if history:
            self.session_history = history
            self.current_session_path = session_path
            self.save_session_to_file()
            self.log("새로운 세션이 성공적으로 생성되고 파일로 저장되었습니다.")
        
        self.clean_up_thread()
        self.set_ui_enabled(True)
        self.update_ui_for_session_status()

    def start_generation(self):
        if self.file_list_widget.count() == 0:
            QMessageBox.warning(self, "입력 오류", "작업할 강의안 파일을 하나 이상 추가해주세요.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "결과를 저장할 폴더 선택")
        if not output_dir: return

        self.set_ui_enabled(False)
        content_files = [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())]
        
        self.thread = QThread()
        self.worker = GeminiWorker(self.api_key_edit.text(), self.model_name_edit.text())
        self.worker.moveToThread(self.thread)

        self.worker.log_message.connect(self.log)
        self.worker.task_finished.connect(self.on_task_finished)
        self.thread.started.connect(lambda: self.worker.process_files(self.session_history, content_files, output_dir))
        
        self.thread.start()

    def on_task_finished(self, updated_history):
        if updated_history:
            self.session_history = updated_history
            self.save_session_to_file()
            self.log("작업 완료 후 업데이트된 세션을 파일에 저장했습니다.")
        
        self.clean_up_thread()
        self.set_ui_enabled(True)

    def add_content_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "강의안 파일 선택", "", "Text Files (*.txt)")
        if files:
            self.file_list_widget.addItems(files)

    def log(self, message):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_widget.appendPlainText(f"[{now}] {message}")

    def set_ui_enabled(self, enabled):
        self.start_button.setEnabled(enabled)
        self.btn_new_session.setEnabled(enabled)
        self.btn_load_session.setEnabled(enabled)
        self.start_button.setText("프롬프트 생성 시작" if enabled else "처리 중...")

    def clean_up_thread(self):
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            self.thread.wait()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())