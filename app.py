# app.py

import os
import json
import sys
import subprocess
import re
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QMessageBox, QFileDialog, QListWidgetItem, QCompleter)
from PySide6.QtCore import Qt, QThreadPool, Slot, QStringListModel, QTimer, QSortFilterProxyModel, QRegularExpression

from data_models import Variable, Task
from ui_components import VariablePanel, TaskPanel, RunPanel
from core_logic import TaskRunner
from variable_handler import VariableHandler
from task_handler import TaskHandler

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini 워크플로우 자동화 도구 v3.2 (연결 버그 수정)")
        self.setGeometry(100, 100, 1400, 900)
        
        self.config_file = "workspace.json"
        self.variables = {}
        self.tasks = {}
        self.is_loading_state = False
        
        self.thread_pool = QThreadPool()
        self.current_runner = None
        
        self.var_panel = VariablePanel()
        self.task_panel = TaskPanel()
        self.run_panel = RunPanel()
        
        self.variable_handler = VariableHandler(self.var_panel, self.variables)
        self.task_handler = TaskHandler(self.task_panel, self.tasks)
        
        self.save_timer = QTimer(self)
        self.all_vars_model = QStringListModel(self)
        self.vars_proxy_model = QSortFilterProxyModel(self)
        self.task_completer = QCompleter(self.all_vars_model, self)
        self.variable_completer = QCompleter(self.vars_proxy_model, self)

        self.setup_ui()
        self.connect_signals()
        
        self.load_state()
        
        self.log(f"PySide6 워크플로우 자동화 도구 시작. 현재 {self.thread_pool.maxThreadCount()}개의 스레드 사용 가능.")
        
        self.update_completer_model_and_filter()
        self.task_handler.on_task_selected(None, None)

    def setup_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.var_panel)
        splitter.addWidget(self.task_panel)
        splitter.addWidget(self.run_panel)
        splitter.setSizes([350, 600, 450])
        
        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter)
        self.setCentralWidget(central_widget)

        self.vars_proxy_model.setSourceModel(self.all_vars_model)
        for completer in [self.task_completer, self.variable_completer]:
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
        
        self.var_panel.value_edit.setCompleter(self.variable_completer)
        self.task_panel.prompt_edit.setCompleter(self.task_completer)
        
        if not os.path.exists(self.config_file):
            self.run_panel.model_name_edit.setText("gemini-1.5-flash-latest")
            self.run_panel.output_folder_edit.setText(os.path.join(os.getcwd(), "output_pyside"))
            self.run_panel.output_ext_edit.setText(".md")

    def connect_signals(self):
        # *** 수정됨: 각 핸들러의 시그널 연결 함수를 호출 ***
        # 1. 각 핸들러가 자신의 UI 이벤트를 처리하도록 연결
        self.variable_handler.connect_signals()
        self.task_handler.connect_signals()
        
        # 2. 핸들러가 보낸 신호를 MainWindow가 받아서 전역 작업을 처리하도록 연결
        self.variable_handler.signals.state_changed.connect(self.schedule_save)
        self.variable_handler.signals.variables_updated.connect(self.update_completer_model_and_filter)
        self.variable_handler.signals.log_message.connect(self.log)
        
        self.task_handler.signals.state_changed.connect(self.schedule_save)
        self.task_handler.signals.log_message.connect(self.log)

        # 3. MainWindow가 직접 처리해야 하는 전역 시그널 연결
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self.save_state)

        # 실행 패널 관련 시그널 (전역 제어)
        self.run_panel.run_btn.clicked.connect(self.start_execution)
        self.run_panel.stop_btn.clicked.connect(self.stop_execution)
        self.run_panel.clear_log_btn.clicked.connect(self.clear_log)
        self.run_panel.select_folder_btn.clicked.connect(self.select_output_folder)
        self.run_panel.open_output_folder_btn.clicked.connect(self.open_output_folder)
        self.run_panel.select_log_folder_btn.clicked.connect(self.select_log_folder)
        self.run_panel.open_log_folder_btn.clicked.connect(self.open_log_folder)
        
        # 설정 변경 시 자동 저장
        for widget in [self.run_panel.api_key_edit, self.run_panel.model_name_edit, 
                       self.run_panel.output_folder_edit, self.run_panel.output_ext_edit,
                       self.run_panel.log_folder_edit]:
            widget.editingFinished.connect(self.schedule_save)
            
    # --- 상태 관리 (저장/로드) ---
    @Slot()
    def schedule_save(self):
        if self.is_loading_state: return
        self.save_timer.start()

    def save_state(self):
        try:
            var_order_ids = [self.var_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.var_panel.list_widget.count())]
            task_order_ids = [self.task_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.task_panel.list_widget.count())]
            state_data = {
                'variables': [self.variables[var_id].to_dict() for var_id in var_order_ids if var_id in self.variables],
                'tasks': [self.tasks[task_id].to_dict() for task_id in task_order_ids if task_id in self.tasks],
                'settings': { 
                    'api_key': self.run_panel.api_key_edit.text(), 
                    'model_name': self.run_panel.model_name_edit.text(), 
                    'output_folder': self.run_panel.output_folder_edit.text(), 
                    'output_extension': self.run_panel.output_ext_edit.text(), 
                    'log_folder': self.run_panel.log_folder_edit.text() 
                }
            }
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(state_data, f, indent=4, ensure_ascii=False)
        except Exception as e: self.log(f"작업 환경 저장 실패: {e}")

    def load_state(self):
        if not os.path.exists(self.config_file): return
        self.is_loading_state = True
        self.variable_handler.is_loading = True
        self.task_handler.is_loading = True

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: state_data = json.load(f)
            self.var_panel.list_widget.clear(); self.variables.clear()
            self.task_panel.list_widget.clear(); self.tasks.clear()
            
            for var_data in state_data.get('variables', []):
                var = Variable(id=var_data.get('id'), name=var_data.get('name'), value=var_data.get('value'))
                if not var.id or not var.name: continue
                self.variables[var.id] = var
                item = QListWidgetItem(var.name); item.setData(Qt.UserRole, var.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable); self.var_panel.list_widget.addItem(item)
            
            for task_data in state_data.get('tasks', []):
                task = Task(id=task_data.get('id'), name=task_data.get('name'), 
                            prompt=task_data.get('prompt'), enabled=task_data.get('enabled', True))
                if not task.id or not task.name: continue
                self.tasks[task.id] = task
                item = QListWidgetItem(task.name); item.setData(Qt.UserRole, task.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked)
                self.task_panel.list_widget.addItem(item)
            
            settings = state_data.get('settings', {})
            self.run_panel.api_key_edit.setText(settings.get('api_key', ''))
            self.run_panel.model_name_edit.setText(settings.get('model_name', 'gemini-1.5-flash-latest'))
            self.run_panel.output_folder_edit.setText(settings.get('output_folder', os.path.join(os.getcwd(), "output_pyside")))
            self.run_panel.output_ext_edit.setText(settings.get('output_extension', '.md'))
            self.run_panel.log_folder_edit.setText(settings.get('log_folder', ''))
            
            self.log(f"저장된 작업 환경 '{self.config_file}'을 불러왔습니다.")
            self.load_last_log_file(settings.get('log_folder', ''))
            
        except Exception as e: QMessageBox.critical(self, "상태 로드 오류", f"'{self.config_file}' 파일을 불러오는 중 오류가 발생했습니다:\n{e}")
        finally: 
            self.is_loading_state = False
            self.variable_handler.is_loading = False
            self.task_handler.is_loading = False

    def closeEvent(self, event):
        reply = QMessageBox.question(self, '종료', "종료하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes: self.save_state(); event.accept()
        else: event.ignore()

    @Slot()
    def update_completer_model_and_filter(self):
        var_names = [var.name for var in self.variables.values()]
        self.all_vars_model.setStringList(var_names)
        self.update_variable_completer_filter()

    def update_variable_completer_filter(self):
        current_item = self.var_panel.list_widget.currentItem()
        if current_item:
            current_var_name = current_item.text()
            pattern = f"^(?!{re.escape(current_var_name)}$).*"
            self.vars_proxy_model.setFilterRegularExpression(QRegularExpression(pattern))
        else:
            self.vars_proxy_model.setFilterRegularExpression(QRegularExpression("$^"))

    @Slot(str)
    def log(self, message):
        self.run_panel.log_viewer.append(message)

    @Slot()
    def clear_log(self):
        self.run_panel.log_viewer.clear()
        self.log("로그가 삭제되었습니다.")
        
    def set_ui_enabled(self, enabled):
        self.var_panel.setEnabled(enabled)
        self.task_panel.setEnabled(enabled)
        for widget in [self.run_panel.api_key_edit, self.run_panel.model_name_edit,
                       self.run_panel.output_folder_edit, self.run_panel.select_folder_btn,
                       self.run_panel.open_output_folder_btn, self.run_panel.output_ext_edit,
                       self.run_panel.log_folder_edit, self.run_panel.select_log_folder_btn,
                       self.run_panel.open_log_folder_btn, self.run_panel.clear_log_btn]:
            widget.setEnabled(enabled)
        
        if enabled:
            self.run_panel.run_btn.show(); self.run_panel.stop_btn.hide()
        else:
            self.run_panel.run_btn.hide(); self.run_panel.stop_btn.show()

    def start_execution(self):
        api_key = self.run_panel.api_key_edit.text()
        if not api_key: QMessageBox.warning(self, "오류", "Gemini API 키를 입력해주세요."); return
        
        tasks_to_run = [self.tasks[self.task_panel.list_widget.item(i).data(Qt.UserRole)] 
                        for i in range(self.task_panel.list_widget.count()) 
                        if self.task_panel.list_widget.item(i).checkState() == Qt.Checked]

        if not tasks_to_run:
            QMessageBox.warning(self, "오류", "실행할 활성화된 태스크가 없습니다."); return
        
        self.set_ui_enabled(False)
        self.current_runner = TaskRunner(
            api_key=api_key, model_name=self.run_panel.model_name_edit.text(), 
            variables=self.variables, tasks_in_order=tasks_to_run, 
            output_folder=self.run_panel.output_folder_edit.text(),
            output_extension=self.run_panel.output_ext_edit.text(), 
            log_folder=self.run_panel.log_folder_edit.text()
        )
        self.current_runner.signals.log_message.connect(self.log)
        self.current_runner.signals.error.connect(lambda e: QMessageBox.critical(self, "실행 오류", str(e)))
        self.current_runner.signals.finished.connect(self.on_execution_finished)
        self.thread_pool.start(self.current_runner)
        
    def stop_execution(self):
        if self.current_runner: 
            self.log("사용자 중지 요청...")
            self.current_runner.stop()
            
    def on_execution_finished(self):
        self.set_ui_enabled(True)
        self.current_runner = None

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "결과 저장 폴더 선택")
        if folder: self.run_panel.output_folder_edit.setText(folder); self.schedule_save()
        
    def select_log_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "로그 저장 폴더 선택")
        if folder: self.run_panel.log_folder_edit.setText(folder); self.schedule_save()

    def load_last_log_file(self, log_folder):
        if not log_folder or not os.path.isdir(log_folder): return
        try:
            log_files = [f for f in os.listdir(log_folder) if f.startswith('log_') and f.endswith('.txt')]
            if not log_files: return
            last_log_file = sorted(log_files)[-1]
            filepath = os.path.join(log_folder, last_log_file)
            with open(filepath, 'r', encoding='utf-8') as f: log_content = f.read()
            self.run_panel.log_viewer.append("--- 이전 로그 불러오기 ---\n" + log_content + "\n------------------------\n")
            self.log(f"이전 로그 파일 '{last_log_file}'을 불러왔습니다.")
        except Exception as e: self.log(f"이전 로그 파일 불러오기 실패: {e}")

    def _open_folder_at_path(self, path):
        if not path or not os.path.isdir(path): 
            QMessageBox.warning(self, "경고", f"유효하지 않은 폴더 경로입니다:\n{path}")
            return
        try:
            if sys.platform == "win32": os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
            self.log(f"폴더 열기: {path}")
        except Exception as e: 
            QMessageBox.critical(self, "오류", f"폴더를 여는 중 오류가 발생했습니다:\n{e}")
            
    def open_output_folder(self): self._open_folder_at_path(self.run_panel.output_folder_edit.text())
    def open_log_folder(self): self._open_folder_at_path(self.run_panel.log_folder_edit.text())