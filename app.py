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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini 워크플로우 자동화 도구 v1.8 (태스크 활성화)") # 버전 업데이트
        self.setGeometry(100, 100, 1400, 900)
        
        # (기존 __init__ 속성들은 변경 없음)
        self.config_file = "workspace.json"
        self.variables = {}
        self.tasks = {}
        self.thread_pool = QThreadPool()
        self.current_runner = None
        self.is_loading_state = False
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self.save_state)
        self.all_vars_model = QStringListModel(self)
        self.task_completer = QCompleter(self.all_vars_model, self)
        self.vars_proxy_model = QSortFilterProxyModel(self)
        self.vars_proxy_model.setSourceModel(self.all_vars_model)
        self.variable_completer = QCompleter(self.vars_proxy_model, self)
        
        self.var_panel = VariablePanel()
        self.task_panel = TaskPanel()
        self.run_panel = RunPanel()
        
        self.setup_ui()
        self.connect_signals()
        
        self.load_state()
        
        self.log(f"PySide6 워크플로우 자동화 도구 시작. 현재 {self.thread_pool.maxThreadCount()}개의 스레드 사용 가능.")
        self.update_completer_model()
        self.on_var_selected(None, None)
        self.on_task_selected(None, None)

    # (save_state는 변경 없음)
    def schedule_save(self):
        if self.is_loading_state: return
        self.save_timer.start()
    def save_state(self):
        try:
            task_order_ids = [self.task_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.task_panel.list_widget.count())]
            state_data = {
                'variables': [var.to_dict() for var in self.variables.values()],
                'tasks': [self.tasks[task_id].to_dict() for task_id in task_order_ids],
                'settings': { 'api_key': self.run_panel.api_key_edit.text(), 'model_name': self.run_panel.model_name_edit.text(), 'output_folder': self.run_panel.output_folder_edit.text(), 'output_extension': self.run_panel.output_ext_edit.text(), 'log_folder': self.run_panel.log_folder_edit.text() }
            }
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(state_data, f, indent=4, ensure_ascii=False)
        except Exception as e: self.log(f"작업 환경 저장 실패: {e}")

    def load_state(self):
        if not os.path.exists(self.config_file): return
        self.is_loading_state = True
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            self.var_panel.list_widget.blockSignals(True)
            self.task_panel.list_widget.blockSignals(True)
            
            for var_data in state_data.get('variables', []):
                var = Variable(id=var_data['id'], name=var_data['name'], value=var_data['value'])
                self.variables[var.id] = var
                item = QListWidgetItem(var.name)
                item.setData(Qt.UserRole, var.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable)
                self.var_panel.list_widget.addItem(item)

            for task_data in state_data.get('tasks', []):
                # *** 수정됨: enabled 속성 로드 (하위 호환성 고려) ***
                task_enabled = task_data.get('enabled', True)
                task = Task(id=task_data['id'], name=task_data['name'], prompt=task_data['prompt'], enabled=task_enabled)
                self.tasks[task.id] = task
                item = QListWidgetItem(task.name)
                item.setData(Qt.UserRole, task.id)
                # *** 수정됨: 체크박스 플래그 및 상태 설정 ***
                item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked)
                self.task_panel.list_widget.addItem(item)
            
            self.var_panel.list_widget.blockSignals(False)
            self.task_panel.list_widget.blockSignals(False)

            settings = state_data.get('settings', {})
            # ... (이하 로직은 변경 없음)
            self.run_panel.api_key_edit.setText(settings.get('api_key', ''))
            self.run_panel.model_name_edit.setText(settings.get('model_name', 'gemini-1.5-flash-latest'))
            self.run_panel.output_folder_edit.setText(settings.get('output_folder', os.path.join(os.getcwd(), "output_pyside")))
            self.run_panel.output_ext_edit.setText(settings.get('output_extension', '.md'))
            self.run_panel.log_folder_edit.setText(settings.get('log_folder', ''))
            self.log(f"저장된 작업 환경 '{self.config_file}'을 불러왔습니다.")
            self.load_last_log_file(settings.get('log_folder', ''))
        except Exception as e: QMessageBox.critical(self, "상태 로드 오류", f"'{self.config_file}' 파일을 불러오는 중 오류가 발생했습니다:\n{e}")
        finally: self.is_loading_state = False

    # (load_last_log_file, closeEvent, setup_ui 등은 변경 없음)
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
    def closeEvent(self, event):
        reply = QMessageBox.question(self, '종료', "종료하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
        if reply == QMessageBox.StandardButton.Yes: self.save_state(); event.accept()
        else: event.ignore()
    def setup_ui(self):
        splitter = QSplitter(Qt.Horizontal); splitter.addWidget(self.var_panel); splitter.addWidget(self.task_panel); splitter.addWidget(self.run_panel)
        splitter.setSizes([350, 600, 450]); central_widget = QWidget(); layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter); self.setCentralWidget(central_widget)
        self.task_panel.prompt_edit.setCompleter(self.task_completer); self.var_panel.value_edit.setCompleter(self.variable_completer)
        for completer in [self.task_completer, self.variable_completer]: completer.setCaseSensitivity(Qt.CaseInsensitive); completer.setFilterMode(Qt.MatchContains)
        if not os.path.exists(self.config_file):
            self.run_panel.model_name_edit.setText("gemini-1.5-flash-latest")
            self.run_panel.output_folder_edit.setText(os.path.join(os.getcwd(), "output_pyside"))
            self.run_panel.output_ext_edit.setText(".md")

    def connect_signals(self):
        # 변수 패널
        self.var_panel.add_btn.clicked.connect(self.add_variable)
        self.var_panel.remove_btn.clicked.connect(self.remove_variable)
        self.var_panel.list_widget.currentItemChanged.connect(self.on_var_selected)
        self.var_panel.list_widget.itemChanged.connect(self.on_variable_item_changed)
        self.var_panel.name_edit.editingFinished.connect(self.update_variable_details)
        self.var_panel.value_edit.textChanged.connect(self.update_variable_details)
        self.var_panel.load_file_btn.clicked.connect(self.load_variable_from_file)
        
        # 태스크 패널
        self.task_panel.add_btn.clicked.connect(self.add_task)
        self.task_panel.remove_btn.clicked.connect(self.remove_task)
        self.task_panel.copy_btn.clicked.connect(self.copy_task)
        self.task_panel.up_btn.clicked.connect(lambda: self.move_task('up'))
        self.task_panel.down_btn.clicked.connect(lambda: self.move_task('down'))
        self.task_panel.list_widget.currentItemChanged.connect(self.on_task_selected)
        self.task_panel.list_widget.itemChanged.connect(self.on_task_item_changed)
        self.task_panel.name_edit.editingFinished.connect(self.update_task_details)
        self.task_panel.prompt_edit.textChanged.connect(self.update_task_details)
        # *** 추가됨: 전체 활성화/비활성화 버튼 시그널 연결 ***
        self.task_panel.check_all_btn.clicked.connect(lambda: self.set_all_tasks_checked(True))
        self.task_panel.uncheck_all_btn.clicked.connect(lambda: self.set_all_tasks_checked(False))
        
        # 실행 패널
        self.run_panel.run_btn.clicked.connect(self.start_execution)
        # ... (이하 시그널 연결은 변경 없음)
        self.run_panel.stop_btn.clicked.connect(self.stop_execution)
        self.run_panel.model_name_edit.editingFinished.connect(self.schedule_save)
        self.run_panel.api_key_edit.editingFinished.connect(self.schedule_save)
        self.run_panel.output_folder_edit.editingFinished.connect(self.schedule_save)
        self.run_panel.output_ext_edit.editingFinished.connect(self.schedule_save)
        self.run_panel.log_folder_edit.editingFinished.connect(self.schedule_save)
        self.run_panel.select_folder_btn.clicked.connect(self.select_output_folder)
        self.run_panel.select_log_folder_btn.clicked.connect(self.select_log_folder)
        self.run_panel.open_output_folder_btn.clicked.connect(self.open_output_folder)
        self.run_panel.open_log_folder_btn.clicked.connect(self.open_log_folder)

    # (열기 기능, set_ui_enabled, update_completer_model, 변수 관련 함수는 대부분 변경 없음)
    def _open_folder_at_path(self, path):
        if not path or not os.path.isdir(path): QMessageBox.warning(self, "경고", f"유효하지 않은 폴더 경로입니다:\n{path}"); return
        try:
            if sys.platform == "win32": os.startfile(os.path.realpath(path))
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
            self.log(f"폴더 열기: {path}")
        except Exception as e: QMessageBox.critical(self, "오류", f"폴더를 여는 중 오류가 발생했습니다:\n{e}")
    def open_output_folder(self): self._open_folder_at_path(self.run_panel.output_folder_edit.text())
    def open_log_folder(self): self._open_folder_at_path(self.run_panel.log_folder_edit.text())
    def set_ui_enabled(self, enabled):
        self.var_panel.setEnabled(enabled); self.task_panel.setEnabled(enabled)
        self.run_panel.api_key_edit.setEnabled(enabled); self.run_panel.model_name_edit.setEnabled(enabled)
        self.run_panel.output_folder_edit.setEnabled(enabled); self.run_panel.select_folder_btn.setEnabled(enabled)
        self.run_panel.open_output_folder_btn.setEnabled(enabled); self.run_panel.output_ext_edit.setEnabled(enabled)
        self.run_panel.log_folder_edit.setEnabled(enabled); self.run_panel.select_log_folder_btn.setEnabled(enabled)
        self.run_panel.open_log_folder_btn.setEnabled(enabled)
        if enabled: self.run_panel.run_btn.show(); self.run_panel.stop_btn.hide()
        else: self.run_panel.run_btn.hide(); self.run_panel.stop_btn.show()
    def update_completer_model(self): self.all_vars_model.setStringList([var.name for var in self.variables.values()])
    def on_var_selected(self, current, previous):
        is_item_selected = current is not None
        self.var_panel.name_edit.setEnabled(is_item_selected); self.var_panel.value_edit.setEnabled(is_item_selected)
        self.var_panel.remove_btn.setEnabled(is_item_selected); self.var_panel.load_file_btn.setEnabled(is_item_selected)
        if current:
            current_var_name = current.text(); pattern = f"^(?!{re.escape(current_var_name)}$).*"
            self.vars_proxy_model.setFilterRegularExpression(QRegularExpression(pattern))
        else: self.vars_proxy_model.setFilterRegularExpression(QRegularExpression("$^"))
        if not current: self.var_panel.name_edit.clear(); self.var_panel.value_edit.clear(); return
        var_id = current.data(Qt.UserRole)
        if var_id in self.variables:
            var = self.variables[var_id]
            self.var_panel.name_edit.blockSignals(True); self.var_panel.value_edit.blockSignals(True)
            self.var_panel.name_edit.setText(var.name); self.var_panel.value_edit.setPlainText(var.value)
            self.var_panel.name_edit.blockSignals(False); self.var_panel.value_edit.blockSignals(False)
    @Slot(str)
    def log(self, message): self.run_panel.log_viewer.append(message)
    def add_variable(self):
        var = Variable(); self.variables[var.id] = var; item = QListWidgetItem(var.name); item.setData(Qt.UserRole, var.id)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.var_panel.list_widget.addItem(item); self.var_panel.list_widget.setCurrentItem(item)
        self.update_completer_model(); self.log(f"변수 '{var.name}' 추가됨"); self.schedule_save()
    def remove_variable(self):
        item = self.var_panel.list_widget.currentItem();
        if not item: return
        var_id = item.data(Qt.UserRole)
        if QMessageBox.question(self, "확인", f"'{item.text()}' 변수를 정말 삭제하시겠습니까?") == QMessageBox.Yes:
            del self.variables[var_id]; self.var_panel.list_widget.takeItem(self.var_panel.list_widget.row(item))
            self.update_completer_model(); self.log(f"변수 '{item.text()}' 삭제됨"); self.schedule_save()
    def update_variable_details(self):
        item = self.var_panel.list_widget.currentItem();
        if not item: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.variables:
            var = self.variables[var_id]; var.value = self.var_panel.value_edit.toPlainText(); new_name = self.var_panel.name_edit.text()
            if var.name != new_name: var.name = new_name; item.setText(new_name)
            else: self.schedule_save()
    @Slot(QListWidgetItem)
    def on_variable_item_changed(self, item):
        if self.is_loading_state or not item: return
        var_id = item.data(Qt.UserRole)
        if var_id in self.variables:
            var = self.variables[var_id]; new_name = item.text()
            if var.name != new_name:
                old_name = var.name
                other_var_names = [v.name for k, v in self.variables.items() if k != var_id]
                if new_name in other_var_names:
                    QMessageBox.warning(self, "이름 중복", f"'{new_name}'은(는) 이미 사용 중인 변수 이름입니다."); item.setText(old_name); return
                self.log(f"변수 이름 변경: '{old_name}' -> '{new_name}'"); var.name = new_name; self.update_completer_model()
                if self.var_panel.list_widget.currentItem() == item:
                    self.var_panel.name_edit.blockSignals(True); self.var_panel.name_edit.setText(new_name); self.var_panel.name_edit.blockSignals(False)
                self.schedule_save()
    def load_variable_from_file(self):
        item = self.var_panel.list_widget.currentItem()
        if not item: return
        filepath, _ = QFileDialog.getOpenFileName(self, "텍스트 파일 선택", "", "Text Files (*.txt);;All Files (*)")
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f: content = f.read()
            self.var_panel.value_edit.insertPlainText(content); self.log(f"'{os.path.basename(filepath)}' 내용을 현재 변수에 추가함"); self.schedule_save()
        except Exception as e: QMessageBox.critical(self, "파일 읽기 오류", str(e))

    # --- 태스크 관련 함수들 (수정됨) ---

    def add_task(self):
        task = Task(); self.tasks[task.id] = task
        item = QListWidgetItem(task.name); item.setData(Qt.UserRole, task.id)
        # *** 수정됨: 체크박스 플래그 및 상태 설정 ***
        item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked)
        self.task_panel.list_widget.addItem(item); self.task_panel.list_widget.setCurrentItem(item)
        self.log(f"태스크 '{task.name}' 추가됨"); self.schedule_save()

    def remove_task(self):
        item = self.task_panel.list_widget.currentItem()
        if not item: return
        task_id = item.data(Qt.UserRole)
        if QMessageBox.question(self, "확인", f"'{item.text()}' 태스크를 정말 삭제하시겠습니까?") == QMessageBox.Yes:
            del self.tasks[task_id]
            self.task_panel.list_widget.takeItem(self.task_panel.list_widget.row(item))
            self.log(f"태스크 '{item.text()}' 삭제됨"); self.schedule_save()

    def copy_task(self):
        item = self.task_panel.list_widget.currentItem()
        if not item: return
        original_task = self.tasks[item.data(Qt.UserRole)]
        new_task = original_task.copy()
        self.tasks[new_task.id] = new_task
        new_item = QListWidgetItem(new_task.name); new_item.setData(Qt.UserRole, new_task.id)
        # *** 수정됨: 체크박스 플래그 및 상태 설정 ***
        new_item.setFlags(new_item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        new_item.setCheckState(Qt.Checked if new_task.enabled else Qt.Unchecked)
        current_row = self.task_panel.list_widget.row(item)
        self.task_panel.list_widget.insertItem(current_row + 1, new_item)
        self.task_panel.list_widget.setCurrentItem(new_item)
        self.log(f"태스크 '{original_task.name}' 복사됨"); self.schedule_save()

    def move_task(self, direction):
        # (변경 없음)
        list_widget = self.task_panel.list_widget; item = list_widget.currentItem()
        if not item: return
        current_row = list_widget.row(item)
        if direction == 'up' and current_row > 0:
            new_row = current_row - 1; list_widget.takeItem(current_row); list_widget.insertItem(new_row, item); list_widget.setCurrentRow(new_row); self.schedule_save()
        elif direction == 'down' and current_row < list_widget.count() - 1:
            new_row = current_row + 1; list_widget.takeItem(current_row); list_widget.insertItem(new_row, item); list_widget.setCurrentRow(new_row); self.schedule_save()
        if 'new_row' in locals(): self.log(f"태스크 순서 변경됨")

    def update_task_details(self):
        # (이름 변경 로직은 itemChanged 슬롯으로 이전되었으므로, 여기서는 프롬프트만 업데이트)
        item = self.task_panel.list_widget.currentItem()
        if not item: return
        task_id = item.data(Qt.UserRole)
        if task_id in self.tasks:
            task = self.tasks[task_id]
            # 이름 업데이트 (패널 -> 데이터)
            new_name = self.task_panel.name_edit.text()
            if task.name != new_name:
                task.name = new_name
                item.setText(new_name) # itemChanged 트리거
            
            # 프롬프트 업데이트 (패널 -> 데이터)
            new_prompt = self.task_panel.prompt_edit.toPlainText()
            if task.prompt != new_prompt:
                task.prompt = new_prompt
                self.schedule_save()

    # *** 추가됨: 전체 태스크 활성화/비활성화 슬롯 ***
    def set_all_tasks_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        action_text = "활성화" if checked else "비활성화"
        # itemChanged 시그널이 반복적으로 발생하는 것을 막기 위해 block
        self.task_panel.list_widget.blockSignals(True)
        for i in range(self.task_panel.list_widget.count()):
            item = self.task_panel.list_widget.item(i)
            item.setCheckState(state)
            task_id = item.data(Qt.UserRole)
            if task_id in self.tasks:
                self.tasks[task_id].enabled = checked
        self.task_panel.list_widget.blockSignals(False)
        self.log(f"모든 태스크를 {action_text}했습니다.")
        self.schedule_save()

    @Slot(QListWidgetItem)
    def on_task_item_changed(self, item):
        # *** 수정됨: 이름 변경과 체크 상태 변경을 모두 처리 ***
        if self.is_loading_state or not item: return

        task_id = item.data(Qt.UserRole)
        if task_id in self.tasks:
            task = self.tasks[task_id]
            
            # 1. 이름 변경 감지 및 처리
            new_name = item.text()
            if task.name != new_name:
                self.log(f"태스크 이름 변경: '{task.name}' -> '{new_name}'")
                task.name = new_name
                if self.task_panel.list_widget.currentItem() == item:
                    self.task_panel.name_edit.blockSignals(True)
                    self.task_panel.name_edit.setText(new_name)
                    self.task_panel.name_edit.blockSignals(False)
                self.schedule_save()

            # 2. 체크 상태 변경 감지 및 처리
            new_enabled_state = (item.checkState() == Qt.Checked)
            if task.enabled != new_enabled_state:
                task.enabled = new_enabled_state
                action_text = "활성화" if new_enabled_state else "비활성화"
                self.log(f"태스크 '{task.name}' {action_text}됨")
                self.schedule_save()
    
    def on_task_selected(self, current, previous):
        # (변경 없음)
        is_item_selected = current is not None
        for btn in [self.task_panel.remove_btn, self.task_panel.copy_btn, self.task_panel.up_btn, self.task_panel.down_btn]:
            btn.setEnabled(is_item_selected)
        self.task_panel.name_edit.setEnabled(is_item_selected); self.task_panel.prompt_edit.setEnabled(is_item_selected)
        if not current: self.task_panel.name_edit.clear(); self.task_panel.prompt_edit.clear(); return
        task_id = current.data(Qt.UserRole)
        if task_id in self.tasks:
            task = self.tasks[task_id]
            self.task_panel.name_edit.blockSignals(True); self.task_panel.prompt_edit.blockSignals(True)
            self.task_panel.name_edit.setText(task.name); self.task_panel.prompt_edit.setPlainText(task.prompt)
            self.task_panel.name_edit.blockSignals(False); self.task_panel.prompt_edit.blockSignals(False)

    def start_execution(self):
        api_key = self.run_panel.api_key_edit.text()
        if not api_key: QMessageBox.warning(self, "오류", "Gemini API 키를 입력해주세요."); return
        
        # *** 수정됨: 활성화된 태스크만 필터링하여 실행 목록 생성 ***
        tasks_to_run = []
        for i in range(self.task_panel.list_widget.count()):
            item = self.task_panel.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                task_id = item.data(Qt.UserRole)
                if task_id in self.tasks:
                    tasks_to_run.append(self.tasks[task_id])

        if not tasks_to_run:
            QMessageBox.warning(self, "오류", "실행할 활성화된 태스크가 없습니다."); return
        
        self.set_ui_enabled(False)
        self.current_runner = TaskRunner(
            api_key=api_key, model_name=self.run_panel.model_name_edit.text(), variables=self.variables,
            tasks_in_order=tasks_to_run, # 필터링된 리스트 전달
            output_folder=self.run_panel.output_folder_edit.text(),
            output_extension=self.run_panel.output_ext_edit.text(), log_folder=self.run_panel.log_folder_edit.text())
        self.current_runner.signals.log_message.connect(self.log)
        self.current_runner.signals.error.connect(lambda e: QMessageBox.critical(self, "실행 오류", e))
        self.current_runner.signals.finished.connect(self.on_execution_finished)
        self.thread_pool.start(self.current_runner)
        
    def stop_execution(self):
        if self.current_runner: self.log("사용자 중지 요청..."); self.current_runner.stop()
        
    def on_execution_finished(self):
        self.set_ui_enabled(True); self.current_runner = None

    # (select_output_folder, select_log_folder는 변경 없음)
    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "결과 저장 폴더 선택")
        if folder: self.run_panel.output_folder_edit.setText(folder); self.schedule_save()
    def select_log_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "로그 저장 폴더 선택")
        if folder: self.run_panel.log_folder_edit.setText(folder); self.schedule_save()