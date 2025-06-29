# app.py

import os
import json
import sys
import subprocess
import re
from dotenv import load_dotenv

from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QMessageBox, QFileDialog, QListWidgetItem)
from PySide6.QtCore import Qt, QThreadPool, Slot, QTimer, QSortFilterProxyModel
# *** 추가됨: QAction, QKeySequence 임포트 ***
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QAction, QKeySequence

from data_models import Variable, Task
from ui_components import VariablePanel, TaskPanel, RunPanel, CompleterTextEdit
from core_logic import TaskRunner
from variable_handler import VariableHandler
from task_handler import TaskHandler

load_dotenv()

BUILT_IN_VARS = {'RESPONSE'}
VAR_TYPE_ROLE = Qt.UserRole + 1

# ... VariableFilterProxyModel 클래스는 변경 없음 ...
class VariableFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._exclude_name = ""; self._exclude_built_in = False
    def set_exclude_name(self, name):
        self._exclude_name = name; self.invalidateFilter()
    def set_exclude_built_in(self, exclude):
        self._exclude_built_in = exclude; self.invalidateFilter()
    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        if self._exclude_name:
            text = self.sourceModel().data(index, Qt.DisplayRole)
            if text == self._exclude_name: return False
        if self._exclude_built_in:
            var_type = self.sourceModel().data(index, VAR_TYPE_ROLE)
            if var_type == 'built-in': return False
        return super().filterAcceptsRow(source_row, source_parent)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # self.setWindowTitle("...") # 제목은 update_window_title에서 동적으로 설정
        self.setGeometry(100, 100, 1400, 900)
        
        # --- 상태 관리 변수 ---
        self.variables = {}; self.tasks = {}
        self.is_loading_state = False
        self.current_project_path = None
        self.is_dirty = False
        
        # --- UI 및 핸들러 ---
        self.var_panel = VariablePanel(); self.task_panel = TaskPanel(); self.run_panel = RunPanel()
        self.variable_handler = VariableHandler(self.var_panel, self.variables, BUILT_IN_VARS)
        self.task_handler = TaskHandler(self.task_panel, self.tasks)
        
        # --- 모델 및 기타 ---
        self.thread_pool = QThreadPool(); self.current_runner = None
        self.all_vars_model = QStandardItemModel(self)
        self.prompt_proxy_model = VariableFilterProxyModel(self)
        self.prompt_proxy_model.setSourceModel(self.all_vars_model)
        self.prompt_proxy_model.set_exclude_built_in(True)
        self.variable_proxy_model = VariableFilterProxyModel(self)
        self.variable_proxy_model.setSourceModel(self.all_vars_model)
        self.variable_proxy_model.set_exclude_built_in(True)
        self.highlighter_editors = []

        # --- 초기화 순서 변경 ---
        self.setup_ui()
        self.setup_menu_bar() # 메뉴바 설정
        self.connect_signals()
        
        self.load_env_settings()
        self.new_project() # 시작 시 빈 프로젝트로 시작

        self.log(f"PySide6 워크플로우 자동화 도구 시작. 현재 {self.thread_pool.maxThreadCount()}개의 스레드 사용 가능.")

    # --- UI 설정 ---
    def setup_ui(self):
        # ... (이전과 동일) ...
        splitter = QSplitter(Qt.Horizontal); splitter.addWidget(self.var_panel); splitter.addWidget(self.task_panel); splitter.addWidget(self.run_panel)
        splitter.setSizes([350, 600, 450]); central_widget = QWidget(); layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter); self.setCentralWidget(central_widget)
        self.var_panel.value_edit.setModel(self.variable_proxy_model)
        self.task_panel.prompt_edit.setModel(self.prompt_proxy_model)
        self.task_panel.output_template_edit.setModel(self.all_vars_model)
        self.highlighter_editors.extend([self.var_panel.value_edit, self.task_panel.prompt_edit, self.task_panel.output_template_edit])
        for editor in self.highlighter_editors:
            editor.completer().setCaseSensitivity(Qt.CaseInsensitive)
            editor.completer().setFilterMode(Qt.MatchContains)
        if not os.path.exists("workspace.json"): # 임시 파일 이름 확인
            self.run_panel.model_name_edit.setText("gemini-1.5-flash-latest")
            self.run_panel.output_folder_edit.setText(os.path.join(os.getcwd(), "output_pyside"))
            self.run_panel.output_ext_edit.setText(".md")
            
    # *** 추가됨: 메뉴바 생성 및 설정 ***
    def setup_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        new_action = QAction("&New Project", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_project_action)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Project...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_project_action)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as_project)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
    def connect_signals(self):
        self.variable_handler.connect_signals()
        self.task_handler.connect_signals()
        
        # *** 수정됨: 데이터 변경 시 mark_as_dirty 호출 ***
        self.variable_handler.signals.state_changed.connect(self.mark_as_dirty)
        self.variable_handler.signals.variables_updated.connect(self.update_completer_model_and_filter)
        self.variable_handler.signals.log_message.connect(self.log)
        
        self.task_handler.signals.state_changed.connect(self.mark_as_dirty)
        self.task_handler.signals.log_message.connect(self.log)

        # 실행 패널의 설정 변경도 dirty 상태로 만듦
        for widget in [self.run_panel.model_name_edit, self.run_panel.output_folder_edit, 
                       self.run_panel.output_ext_edit, self.run_panel.log_folder_edit]:
            widget.editingFinished.connect(self.mark_as_dirty)

        # MainWindow가 직접 처리하는 시그널들
        self.run_panel.run_btn.clicked.connect(self.start_execution)
        self.run_panel.stop_btn.clicked.connect(self.stop_execution)
        self.run_panel.clear_log_btn.clicked.connect(self.clear_log)
        self.run_panel.select_folder_btn.clicked.connect(lambda: self.select_folder_for(self.run_panel.output_folder_edit))
        self.run_panel.open_output_folder_btn.clicked.connect(self.open_output_folder)
        self.run_panel.select_log_folder_btn.clicked.connect(lambda: self.select_folder_for(self.run_panel.log_folder_edit))
        self.run_panel.open_log_folder_btn.clicked.connect(self.open_log_folder)

    # --- 상태 및 프로젝트 관리 함수 ---
    @Slot()
    def mark_as_dirty(self):
        """데이터가 변경되었음을 표시합니다."""
        if self.is_loading_state: return
        self.is_dirty = True
        self.update_window_title()

    def update_window_title(self):
        """현재 프로젝트 상태에 맞게 윈도우 제목을 업데이트합니다."""
        title = "Untitled Project"
        if self.current_project_path:
            title = os.path.basename(self.current_project_path)
        
        if self.is_dirty:
            title += "*"
            
        self.setWindowTitle(f"{title} - Gemini 워크플로우 자동화 도구")

    def check_before_proceed(self, action_name="작업"):
        """다른 작업을 진행하기 전에 저장되지 않은 변경사항을 확인합니다."""
        if not self.is_dirty:
            return True # 저장할 것 없으면 계속 진행
        
        reply = QMessageBox.question(self, "변경 내용 저장", 
                                     f"'{action_name}'을(를) 계속하기 전에 변경 내용을 저장하시겠습니까?",
                                     QMessageBox.StandardButton.Save | 
                                     QMessageBox.StandardButton.Discard | 
                                     QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Save:
            return self.save_project() # 저장 성공 여부를 반환
        elif reply == QMessageBox.StandardButton.Cancel:
            return False # 작업 취소
        
        return True # Discard (버리기)

    @Slot()
    def new_project_action(self):
        if self.check_before_proceed("새 프로젝트 생성"):
            self.new_project()

    def new_project(self):
        """모든 작업 공간을 깨끗하게 초기화합니다."""
        self.is_loading_state = True
        self.variable_handler.is_loading = True
        self.task_handler.is_loading = True
        
        self.var_panel.list_widget.clear(); self.variables.clear()
        self.task_panel.list_widget.clear(); self.tasks.clear()
        
        # UI 패널 초기화
        self.task_handler.on_task_selected(None, None)
        self.variable_handler.on_var_selected(None, None)

        self.current_project_path = None
        self.is_dirty = False
        self.update_window_title()
        self.update_completer_model_and_filter()

        self.is_loading_state = False
        self.variable_handler.is_loading = False
        self.task_handler.is_loading = False
        self.log("새 프로젝트가 생성되었습니다.")

    @Slot()
    def open_project_action(self):
        if self.check_before_proceed("프로젝트 열기"):
            path, _ = QFileDialog.getOpenFileName(self, "프로젝트 열기", "", "Workflow Files (*.json);;All Files (*)")
            if path:
                self.load_state(path)

    @Slot()
    def save_project(self):
        """현재 프로젝트를 저장합니다. 경로가 없으면 다른 이름으로 저장을 호출합니다."""
        if self.current_project_path is None:
            return self.save_as_project()
        else:
            return self.save_state(self.current_project_path)
            
    @Slot()
    def save_as_project(self):
        """다른 이름으로 프로젝트를 저장합니다."""
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "", "Workflow Files (*.json);;All Files (*)")
        if path:
            self.current_project_path = path
            return self.save_state(path)
        return False # 사용자가 취소한 경우

    # --- 파일 I/O 로직 (경로를 인자로 받도록 수정) ---
    def save_state(self, path):
        try:
            var_order_ids = [self.var_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.var_panel.list_widget.count())]
            task_order_ids = [self.task_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.task_panel.list_widget.count())]
            state_data = {
                'variables': [self.variables[var_id].to_dict() for var_id in var_order_ids if var_id in self.variables],
                'tasks': [self.tasks[task_id].to_dict() for task_id in task_order_ids if task_id in self.tasks],
                'settings': { 'model_name': self.run_panel.model_name_edit.text(), 
                              'output_folder': self.run_panel.output_folder_edit.text(), 
                              'output_extension': self.run_panel.output_ext_edit.text(), 
                              'log_folder': self.run_panel.log_folder_edit.text() }}
            with open(path, 'w', encoding='utf-8') as f: json.dump(state_data, f, indent=4, ensure_ascii=False)
            
            self.is_dirty = False
            self.update_window_title()
            self.log(f"프로젝트 '{os.path.basename(path)}'가 저장되었습니다.")
            return True
        except Exception as e:
            self.log(f"프로젝트 저장 실패: {e}")
            QMessageBox.critical(self, "저장 오류", f"프로젝트를 저장하는 중 오류가 발생했습니다:\n{e}")
            return False

    def load_state(self, path):
        self.new_project() # 불러오기 전에 현재 작업 공간을 깨끗이 비움
        self.is_loading_state = True; self.variable_handler.is_loading = True; self.task_handler.is_loading = True
        try:
            with open(path, 'r', encoding='utf-8') as f: state_data = json.load(f)
            # ... (이하 로직은 이전과 동일) ...
            for var_data in state_data.get('variables', []):
                if var_data.get('name', '').upper() in BUILT_IN_VARS: continue
                var = Variable(id=var_data.get('id'), name=var_data.get('name'), value=var_data.get('value'))
                if not var.id or not var.name: continue
                self.variables[var.id] = var; item = QListWidgetItem(var.name); item.setData(Qt.UserRole, var.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable); self.var_panel.list_widget.addItem(item)
            for task_data in state_data.get('tasks', []):
                task = Task(id=task_data.get('id'), name=task_data.get('name'), 
                            prompt=task_data.get('prompt'), enabled=task_data.get('enabled', True),
                            output_template=task_data.get('output_template', ''))
                if not task.id or not task.name: continue
                self.tasks[task.id] = task; item = QListWidgetItem(task.name); item.setData(Qt.UserRole, task.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked); self.task_panel.list_widget.addItem(item)
            settings = state_data.get('settings', {}); 
            self.run_panel.model_name_edit.setText(settings.get('model_name', 'gemini-1.5-flash-latest'))
            self.run_panel.output_folder_edit.setText(settings.get('output_folder', os.path.join(os.getcwd(), "output_pyside")))
            self.run_panel.output_ext_edit.setText(settings.get('output_extension', '.md'))
            self.run_panel.log_folder_edit.setText(settings.get('log_folder', ''))
            
            self.current_project_path = path
            self.is_dirty = False
            self.update_window_title()
            self.update_completer_model_and_filter()
            self.log(f"프로젝트 '{os.path.basename(path)}'를 불러왔습니다.")
            
        except Exception as e:
            self.new_project() # 로드 실패 시 깨끗한 상태로 복귀
            QMessageBox.critical(self, "프로젝트 열기 오류", f"'{os.path.basename(path)}' 파일을 불러오는 중 오류가 발생했습니다:\n{e}")
        finally: 
            self.is_loading_state = False; self.variable_handler.is_loading = False; self.task_handler.is_loading = False

    def closeEvent(self, event):
        if self.check_before_proceed("프로그램 종료"):
            # 전역 설정 저장 (예: 창 크기) - 나중에 구현
            event.accept()
        else:
            event.ignore()

    # --- 기타 유틸리티 및 슬롯 ---
    # ... (이전과 동일) ...
    def load_env_settings(self):
        api_key = os.getenv("GEMINI_API_KEY"); project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
        if api_key: self.run_panel.api_key_edit.setText(api_key); self.log(".env: API 키를 불러왔습니다.")
        else: self.log(".env: GEMINI_API_KEY가 설정되지 않았습니다.")
        if project_id and location: self.log(f".env: Project ID({project_id})와 Location({location})을 불러왔습니다.")
        else: self.log(".env: Context Caching에 필요한 PROJECT_ID 또는 LOCATION이 설정되지 않았습니다.")
    def select_folder_for(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder: line_edit.setText(folder); self.mark_as_dirty()
    # (나머지 함수들은 이전 버전에서 복사-붙여넣기 하면 됩니다)
    @Slot()
    def update_completer_model_and_filter(self):
        self.all_vars_model.clear()
        valid_var_names = BUILT_IN_VARS.copy()
        for var in self.variables.values():
            valid_var_names.add(var.name)
        for var_name in sorted(list(BUILT_IN_VARS)):
            item = QStandardItem(var_name); item.setData(QColor("#4a90e2"), Qt.ForegroundRole)
            item.setToolTip(f"내장 변수: {var_name}"); item.setData('built-in', VAR_TYPE_ROLE)
            self.all_vars_model.appendRow(item)
        for var in sorted(self.variables.values(), key=lambda v: v.name):
            item = QStandardItem(var.name); item.setData('user', VAR_TYPE_ROLE)
            self.all_vars_model.appendRow(item)
        self.update_variable_completer_filter()
        for editor in self.highlighter_editors:
            editor.highlighter.set_valid_variables(valid_var_names)
    def update_variable_completer_filter(self):
        current_item = self.var_panel.list_widget.currentItem()
        if current_item:
            current_var_name = current_item.text()
            self.variable_proxy_model.set_exclude_name(current_var_name)
        else: self.variable_proxy_model.set_exclude_name("")
    @Slot(str)
    def log(self, message): self.run_panel.log_viewer.append(message)
    @Slot()
    def clear_log(self): self.run_panel.log_viewer.clear(); self.log("로그가 삭제되었습니다.")
    def set_ui_enabled(self, enabled):
        self.var_panel.setEnabled(enabled); self.task_panel.setEnabled(enabled)
        for widget in [self.run_panel.api_key_edit, self.run_panel.model_name_edit, self.run_panel.output_folder_edit, 
                       self.run_panel.select_folder_btn, self.run_panel.open_output_folder_btn, self.run_panel.output_ext_edit,
                       self.run_panel.log_folder_edit, self.run_panel.select_log_folder_btn, self.run_panel.open_log_folder_btn, 
                       self.run_panel.clear_log_btn]:
            widget.setEnabled(enabled)
        if enabled: self.run_panel.run_btn.show(); self.run_panel.stop_btn.hide()
        else: self.run_panel.run_btn.hide(); self.run_panel.stop_btn.show()
    def start_execution(self):
        api_key = self.run_panel.api_key_edit.text()
        if not api_key: QMessageBox.warning(self, "오류", "Gemini API 키를 입력해주세요."); return
        tasks_to_run = [self.tasks[self.task_panel.list_widget.item(i).data(Qt.UserRole)] 
                        for i in range(self.task_panel.list_widget.count()) if self.task_panel.list_widget.item(i).checkState() == Qt.Checked]
        if not tasks_to_run: QMessageBox.warning(self, "오류", "실행할 활성화된 태스크가 없습니다."); return
        self.set_ui_enabled(False)
        self.current_runner = TaskRunner(api_key=api_key, model_name=self.run_panel.model_name_edit.text(), variables=self.variables, 
                                       tasks_in_order=tasks_to_run, output_folder=self.run_panel.output_folder_edit.text(),
                                       output_extension=self.run_panel.output_ext_edit.text(), log_folder=self.run_panel.log_folder_edit.text())
        self.current_runner.signals.log_message.connect(self.log)
        self.current_runner.signals.error.connect(lambda e: QMessageBox.critical(self, "실행 오류", str(e)))
        self.current_runner.signals.finished.connect(self.on_execution_finished); self.thread_pool.start(self.current_runner)
    def stop_execution(self):
        if self.current_runner: self.log("사용자 중지 요청..."); self.current_runner.stop()
    def on_execution_finished(self): self.set_ui_enabled(True); self.current_runner = None
    def open_output_folder(self): self._open_folder_at_path(self.run_panel.output_folder_edit.text())
    def open_log_folder(self): self._open_folder_at_path(self.run_panel.log_folder_edit.text())
    def load_last_log_file(self, log_folder):
        if not log_folder or not os.path.isdir(log_folder): return
        try:
            log_files = [f for f in os.listdir(log_folder) if f.startswith('log_') and f.endswith('.txt')]
            if not log_files: return
            last_log_file = sorted(log_files)[-1]; filepath = os.path.join(log_folder, last_log_file)
            with open(filepath, 'r', encoding='utf-8') as f: log_content = f.read()
            self.run_panel.log_viewer.append("--- 이전 로그 불러오기 ---\n" + log_content + "\n------------------------\n")
            self.log(f"이전 로그 파일 '{last_log_file}'을 불러왔습니다.")
        except Exception as e: self.log(f"이전 로그 파일 불러오기 실패: {e}")
    def _open_folder_at_path(self, path):
        if not path or not os.path.isdir(path): QMessageBox.warning(self, "경고", f"유효하지 않은 폴더 경로입니다:\n{path}"); return
        try:
            if sys.platform == "win32": os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
            self.log(f"폴더 열기: {path}")
        except Exception as e: QMessageBox.critical(self, "오류", f"폴더를 여는 중 오류가 발생했습니다:\n{e}")