# app.py

import os
import json
import sys
import subprocess
import re
from dotenv import load_dotenv
import datetime

from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter, 
                             QMessageBox, QFileDialog, QListWidgetItem, QComboBox)
from PySide6.QtCore import Qt, QThreadPool, Slot, QTimer, QSortFilterProxyModel, QRunnable, QObject, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QAction, QKeySequence

import vertexai
from vertexai.preview import caching

from data_models import Variable, Task
from ui_components import VariablePanel, TaskPanel, RunPanel, CompleterTextEdit
from core_logic import TaskRunner
from variable_handler import VariableHandler
from task_handler import TaskHandler
from cache_manager_dialog import CacheManagerDialog

load_dotenv()

BUILT_IN_VARS = {'RESPONSE'}
SUPPORTED_MODELS = [
    "gemini-1.5-pro",
    "gemini-1.5-flash"
]
VAR_TYPE_ROLE = Qt.UserRole + 1

# ... VariableFilterProxyModel, CacheFetcher, CacheDetailsFetcher, CacheDeleter 클래스는 변경 없음 ...
class VariableFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent); self._exclude_name = ""; self._exclude_built_in = False
    def set_exclude_name(self, name): self._exclude_name = name; self.invalidateFilter()
    def set_exclude_built_in(self, exclude): self._exclude_built_in = exclude; self.invalidateFilter()
    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        if self._exclude_name:
            if self.sourceModel().data(index, Qt.DisplayRole) == self._exclude_name: return False
        if self._exclude_built_in:
            if self.sourceModel().data(index, VAR_TYPE_ROLE) == 'built-in': return False
        return super().filterAcceptsRow(source_row, source_parent)
class CacheFetcherSignals(QObject):
    finished = Signal(dict); error = Signal(str)
class CacheFetcher(QRunnable):
    def __init__(self): super().__init__(); self.signals = CacheFetcherSignals()
    @Slot()
    def run(self):
        try:
            project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION"); api_key = os.getenv("GEMINI_API_KEY")
            if not all([project_id, location, api_key]): raise ValueError(".env 파일에 PROJECT_ID, LOCATION, GEMINI_API_KEY가 모두 설정되어야 합니다.")
            vertexai.init(project=project_id, location=location)
            caches = {}
            for cache in caching.CachedContent.list():
                display_name = cache.display_name if cache.display_name else os.path.basename(cache.name)
                model_name = os.path.basename(cache.model_name)
                caches[cache.name] = {'display_name': display_name, 'model_name': model_name}
            self.signals.finished.emit(caches)
        except Exception as e: self.signals.error.emit(f"캐시 목록 로드 실패: {e}")
class CacheDetailsFetcherSignals(QObject):
    finished = Signal(object); error = Signal(str)
class CacheDetailsFetcher(QRunnable):
    def __init__(self, cache_name): super().__init__(); self.signals = CacheDetailsFetcherSignals(); self.cache_name = cache_name
    @Slot()
    def run(self):
        try:
            project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
            if not all([project_id, location]): raise ValueError(".env 설정 필요")
            vertexai.init(project=project_id, location=location)
            cache = caching.CachedContent.get(self.cache_name)
            self.signals.finished.emit(cache)
        except Exception as e: self.signals.error.emit(f"캐시 상세 정보 로드 실패: {e}")
class CacheDeleterSignals(QObject):
    finished = Signal(str); error = Signal(str)
class CacheDeleter(QRunnable):
    def __init__(self, cache_name): super().__init__(); self.signals = CacheDeleterSignals(); self.cache_name = cache_name
    @Slot()
    def run(self):
        try:
            project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
            if not all([project_id, location]): raise ValueError(".env 설정 필요")
            vertexai.init(project=project_id, location=location)
            cache_to_delete = caching.CachedContent(self.cache_name); cache_to_delete.delete()
            self.signals.finished.emit(self.cache_name)
        except Exception as e: self.signals.error.emit(f"캐시 삭제 실패: {e}")

class CacheUpdaterSignals(QObject):
    finished = Signal(object); error = Signal(str)

class CacheUpdater(QRunnable):
    # *** 수정됨: 제공해주신 코드로 교체 ***
    def __init__(self, cache_name, new_ttl):
        super().__init__(); self.signals = CacheUpdaterSignals()
        self.cache_name = cache_name; self.new_ttl = new_ttl
    @Slot()
    def run(self):
        try:
            project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
            if not all([project_id, location]): raise ValueError(".env 설정 필요")
            vertexai.init(project=project_id, location=location)
            cache_to_update = caching.CachedContent.get(self.cache_name)
            
            if not self.new_ttl:
                raise ValueError("업데이트할 TTL 값이 없습니다.")

            cache_to_update.update(ttl=self.new_ttl)
            updated_cache = caching.CachedContent.get(self.cache_name)
            
            self.signals.finished.emit(updated_cache)
        except Exception as e:
            self.signals.error.emit(f"캐시 업데이트 실패: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gemini 워크플로우 자동화 도구 v9.9 (TTL 업데이트 수정)")
        self.setGeometry(100, 100, 1400, 900)
        
        self.config_file = "workspace.json"; self.variables = {}; self.tasks = {}; self.is_loading_state = False
        self.current_project_path = None; self.is_dirty = False
        self.thread_pool = QThreadPool(); self.current_runner = None
        self.var_panel = VariablePanel(); self.task_panel = TaskPanel(); self.run_panel = RunPanel()
        self.variable_handler = VariableHandler(self.var_panel, self.variables, BUILT_IN_VARS)
        self.task_handler = TaskHandler(self.task_panel, self.tasks)
        self.save_timer = QTimer(self); self.all_vars_model = QStandardItemModel(self)
        self.prompt_proxy_model = VariableFilterProxyModel(self); self.prompt_proxy_model.setSourceModel(self.all_vars_model); self.prompt_proxy_model.set_exclude_built_in(True)
        self.variable_proxy_model = VariableFilterProxyModel(self); self.variable_proxy_model.setSourceModel(self.all_vars_model); self.variable_proxy_model.set_exclude_built_in(True)
        self.highlighter_editors = []; self.cache_manager_dialog = None 
        self.setup_ui(); self.setup_menu_bar(); self.connect_signals()
        self.load_env_settings(); self.new_project()
        self.log(f"PySide6 워크플로우 자동화 도구 시작. 현재 {self.thread_pool.maxThreadCount()}개의 스레드 사용 가능.")

    def setup_ui(self):
        splitter = QSplitter(Qt.Horizontal); splitter.addWidget(self.var_panel); splitter.addWidget(self.task_panel); splitter.addWidget(self.run_panel)
        splitter.setSizes([350, 600, 450]); central_widget = QWidget(); layout = QHBoxLayout(central_widget)
        layout.addWidget(splitter); self.setCentralWidget(central_widget)
        self.var_panel.value_edit.setModel(self.variable_proxy_model)
        self.task_panel.prompt_edit.setModel(self.prompt_proxy_model)
        self.task_panel.output_template_edit.setModel(self.all_vars_model)
        self.highlighter_editors.extend([self.var_panel.value_edit, self.task_panel.prompt_edit, self.task_panel.output_template_edit])
        for editor in self.highlighter_editors:
            editor.completer().setCaseSensitivity(Qt.CaseInsensitive); editor.completer().setFilterMode(Qt.MatchContains)
        self.run_panel.model_selector_combo.addItems(SUPPORTED_MODELS)
        
    def setup_menu_bar(self):
        menu_bar = self.menuBar(); file_menu = menu_bar.addMenu("&File")
        new_action = QAction("&New Project", self); new_action.setShortcut(QKeySequence.StandardKey.New); new_action.triggered.connect(self.new_project_action); file_menu.addAction(new_action)
        open_action = QAction("&Open Project...", self); open_action.setShortcut(QKeySequence.StandardKey.Open); open_action.triggered.connect(self.open_project_action); file_menu.addAction(open_action)
        file_menu.addSeparator()
        save_action = QAction("&Save", self); save_action.setShortcut(QKeySequence.StandardKey.Save); save_action.triggered.connect(self.save_project); file_menu.addAction(save_action)
        save_as_action = QAction("Save &As...", self); save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs); save_as_action.triggered.connect(self.save_as_project); file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        tools_menu = menu_bar.addMenu("&Tools")
        cache_manager_action = QAction("Context Cache 관리...", self); cache_manager_action.triggered.connect(self.open_cache_manager); tools_menu.addAction(cache_manager_action)
        
    def connect_signals(self):
        self.variable_handler.connect_signals(); self.task_handler.connect_signals()
        self.variable_handler.signals.state_changed.connect(self.mark_as_dirty)
        self.variable_handler.signals.variables_updated.connect(self.update_completer_model_and_filter)
        self.variable_handler.signals.log_message.connect(self.log)
        self.task_handler.signals.state_changed.connect(self.mark_as_dirty)
        self.task_handler.signals.log_message.connect(self.log)
        self.run_panel.refresh_cache_btn.clicked.connect(self.refresh_caches)
        self.run_panel.cache_selector_combo.currentIndexChanged.connect(self.on_cache_selected)
        for widget in [self.run_panel.model_selector_combo, self.run_panel.output_folder_edit, 
                       self.run_panel.output_ext_edit, self.run_panel.log_folder_edit]:
            if isinstance(widget, QComboBox): widget.currentIndexChanged.connect(self.mark_as_dirty)
            else: widget.editingFinished.connect(self.mark_as_dirty)
        self.run_panel.run_btn.clicked.connect(self.start_execution); self.run_panel.stop_btn.clicked.connect(self.stop_execution)
        self.run_panel.clear_log_btn.clicked.connect(self.clear_log)
        self.run_panel.select_folder_btn.clicked.connect(lambda: self.select_folder_for(self.run_panel.output_folder_edit))
        self.run_panel.open_output_folder_btn.clicked.connect(self.open_output_folder)
        self.run_panel.select_log_folder_btn.clicked.connect(lambda: self.select_folder_for(self.run_panel.log_folder_edit))
        self.run_panel.open_log_folder_btn.clicked.connect(self.open_log_folder)

    @Slot()
    def open_cache_manager(self):
        if not self.cache_manager_dialog:
            self.cache_manager_dialog = CacheManagerDialog(self)
            self.cache_manager_dialog.refresh_requested.connect(self.refresh_caches_for_manager)
            self.cache_manager_dialog.details_requested.connect(self.fetch_cache_details)
            self.cache_manager_dialog.delete_requested.connect(self.delete_cache)
            self.cache_manager_dialog.update_ttl_requested.connect(self.update_cache_ttl)
        self.cache_manager_dialog.show(); self.cache_manager_dialog.raise_(); self.cache_manager_dialog.activateWindow()
        self.refresh_caches_for_manager()

    @Slot()
    def refresh_caches_for_manager(self):
        project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
        if not project_id or not location:
            QMessageBox.warning(self, "환경 변수 오류", ".env 파일에 PROJECT_ID와 LOCATION을 설정해야 합니다."); return
        self.log("관리자: 캐시 목록을 불러오는 중...")
        fetcher = CacheFetcher(); fetcher.signals.finished.connect(self.cache_manager_dialog.update_cache_list)
        fetcher.signals.error.connect(self.cache_manager_dialog.show_error); self.thread_pool.start(fetcher)

    @Slot(str)
    def fetch_cache_details(self, cache_name):
        details_fetcher = CacheDetailsFetcher(cache_name)
        details_fetcher.signals.finished.connect(self.cache_manager_dialog.update_details_view)
        details_fetcher.signals.error.connect(self.cache_manager_dialog.show_error); self.thread_pool.start(details_fetcher)

    @Slot(str)
    def delete_cache(self, cache_name):
        self.log(f"관리자: '{os.path.basename(cache_name)}' 캐시 삭제 중...")
        deleter = CacheDeleter(cache_name)
        deleter.signals.finished.connect(self.on_cache_deleted)
        deleter.signals.error.connect(self.on_cache_action_error); self.thread_pool.start(deleter)

    @Slot(str, datetime.timedelta)
    def update_cache_ttl(self, cache_name, new_ttl):
        self.log(f"관리자: '{os.path.basename(cache_name)}' 캐시 TTL 업데이트 중...")
        updater = CacheUpdater(cache_name, new_ttl)
        updater.signals.finished.connect(self.on_cache_updated)
        updater.signals.error.connect(self.on_cache_action_error)
        self.thread_pool.start(updater)
        
    @Slot(object)
    def on_cache_updated(self, updated_cache_object):
        self.log(f"관리자: 캐시가 성공적으로 업데이트되었습니다.")
        if self.cache_manager_dialog and self.cache_manager_dialog.isVisible():
            self.cache_manager_dialog.update_details_view(updated_cache_object)
        self.refresh_caches()

    @Slot(str)
    def on_cache_deleted(self, deleted_cache_name):
        self.log(f"관리자: '{os.path.basename(deleted_cache_name)}' 캐시가 성공적으로 삭제되었습니다.")
        self.refresh_caches_for_manager(); self.refresh_caches()

    @Slot(str)
    def on_cache_action_error(self, error_msg):
        self.log(error_msg); QMessageBox.critical(self, "캐시 작업 오류", error_msg)
        self.refresh_caches_for_manager()
        
    def load_env_settings(self):
        api_key = os.getenv("GEMINI_API_KEY"); project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
        if api_key: self.run_panel.api_key_edit.setText(api_key); self.log(".env: API 키를 불러왔습니다.")
        else: self.run_panel.api_key_edit.clear(); self.log(".env: GEMINI_API_KEY가 설정되지 않았습니다.")
        if project_id and location: self.log(f".env: Project ID({project_id})와 Location({location})을 불러왔습니다.")
        else: self.log(".env: Context Caching에 필요한 PROJECT_ID 또는 LOCATION이 설정되지 않았습니다.")
        
    @Slot()
    def refresh_caches(self):
        project_id = os.getenv("PROJECT_ID"); location = os.getenv("LOCATION")
        if not project_id or not location:
            if self.isVisible(): QMessageBox.warning(self, "환경 변수 오류", ".env 파일에 PROJECT_ID와 LOCATION을 설정해야 합니다.")
            return
        self.log("캐시 목록을 불러오는 중..."); self.run_panel.refresh_cache_btn.setEnabled(False)
        fetcher = CacheFetcher(); fetcher.signals.finished.connect(self.on_caches_fetched)
        fetcher.signals.error.connect(self.on_cache_fetch_error); self.thread_pool.start(fetcher)
        
    @Slot(dict)
    def on_caches_fetched(self, caches):
        self.log(f"{len(caches)}개의 캐시를 찾았습니다."); self.run_panel.refresh_cache_btn.setEnabled(True)
        combo = self.run_panel.cache_selector_combo; combo.blockSignals(True)
        current_selection = combo.currentData(); combo.clear()
        combo.addItem("(캐시 사용 안 함)", None)
        for name, data in sorted(caches.items(), key=lambda item: item[1]['display_name']):
            display_text = f"{data['display_name']} ({data['model_name']})"
            combo.addItem(display_text, {'name': name, 'model': data['model_name']})
        if current_selection:
            index = combo.findData(current_selection)
            if index != -1: combo.setCurrentIndex(index)
            else: self.log(f"경고: 이전에 선택했던 캐시 '{current_selection.get('name')}'를 찾을 수 없습니다.")
        combo.blockSignals(False); self.on_cache_selected(combo.currentIndex())
        
    @Slot(str)
    def on_cache_fetch_error(self, error_msg):
        self.log(error_msg); 
        if self.isVisible(): QMessageBox.critical(self, "캐시 로드 오류", error_msg)
        self.run_panel.refresh_cache_btn.setEnabled(True)
        
    @Slot(int)
    def on_cache_selected(self, index):
        if index == -1: return
        combo = self.run_panel.cache_selector_combo; cache_data = combo.itemData(index)
        model_combo = self.run_panel.model_selector_combo
        if cache_data:
            if model_combo.findText(cache_data['model']) == -1: model_combo.addItem(cache_data['model'])
            model_combo.setCurrentText(cache_data['model'])
            model_combo.setEnabled(False); model_combo.setToolTip("Context Cache 사용 시 모델은 자동으로 선택됩니다.")
        else:
            for i in range(model_combo.count() -1, -1, -1):
                if model_combo.itemText(i) not in SUPPORTED_MODELS: model_combo.removeItem(i)
            model_combo.setEnabled(True); model_combo.setToolTip("")
        self.mark_as_dirty()
        
    @Slot()
    def mark_as_dirty(self):
        if self.is_loading_state: return
        self.is_dirty = True; self.update_window_title()
        
    def update_window_title(self):
        title = "Untitled Project"
        if self.current_project_path: title = os.path.basename(self.current_project_path)
        if self.is_dirty: title += "*"
        self.setWindowTitle(f"{title} - Gemini 워크플로우 자동화 도구")
        
    def check_before_proceed(self, action_name="작업"):
        if not self.is_dirty: return True
        reply = QMessageBox.question(self, "변경 내용 저장", f"'{action_name}'을(를) 계속하기 전에 변경 내용을 저장하시겠습니까?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if reply == QMessageBox.StandardButton.Save: return self.save_project()
        elif reply == QMessageBox.StandardButton.Cancel: return False
        return True
        
    @Slot()
    def new_project_action(self):
        if self.check_before_proceed("새 프로젝트 생성"): self.new_project()
        
    def new_project(self):
        self.is_loading_state = True; self.variable_handler.is_loading = True; self.task_handler.is_loading = True
        self.var_panel.list_widget.clear(); self.variables.clear(); self.task_panel.list_widget.clear(); self.tasks.clear()
        self.run_panel.cache_selector_combo.clear()
        self.task_handler.on_task_selected(None, None); self.variable_handler.on_var_selected(None, None)
        self.current_project_path = None; self.is_dirty = False; self.update_window_title(); self.update_completer_model_and_filter()
        if len(SUPPORTED_MODELS) > 0: self.run_panel.model_selector_combo.setCurrentText(SUPPORTED_MODELS[0])
        self.is_loading_state = False; self.variable_handler.is_loading = False; self.task_handler.is_loading = False
        self.log("새 프로젝트가 생성되었습니다.")
        
    @Slot()
    def open_project_action(self):
        if self.check_before_proceed("프로젝트 열기"):
            path, _ = QFileDialog.getOpenFileName(self, "프로젝트 열기", "", "Workflow Files (*.json);;All Files (*)")
            if path: self.load_state(path)
            
    @Slot()
    def save_project(self):
        if self.current_project_path is None: return self.save_as_project()
        else: return self.save_state(self.current_project_path)
        
    @Slot()
    def save_as_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", "", "Workflow Files (*.json);;All Files (*)")
        if path: self.current_project_path = path; return self.save_state(path)
        return False
        
    def save_state(self, path):
        try:
            var_order_ids = [self.var_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.var_panel.list_widget.count())]
            task_order_ids = [self.task_panel.list_widget.item(i).data(Qt.UserRole) for i in range(self.task_panel.list_widget.count())]
            cache_data = self.run_panel.cache_selector_combo.currentData()
            state_data = {
                'variables': [self.variables[var_id].to_dict() for var_id in var_order_ids if var_id in self.variables],
                'tasks': [self.tasks[task_id].to_dict() for task_id in task_order_ids if task_id in self.tasks],
                'settings': { 
                    'model_name': self.run_panel.model_selector_combo.currentText(), 'context_cache': cache_data, 
                    'output_folder': self.run_panel.output_folder_edit.text(), 'output_extension': self.run_panel.output_ext_edit.text(), 
                    'log_folder': self.run_panel.log_folder_edit.text() 
                }}
            with open(path, 'w', encoding='utf-8') as f: json.dump(state_data, f, indent=4, ensure_ascii=False)
            self.is_dirty = False; self.update_window_title(); self.log(f"프로젝트 '{os.path.basename(path)}'가 저장되었습니다."); return True
        except Exception as e:
            self.log(f"프로젝트 저장 실패: {e}"); QMessageBox.critical(self, "저장 오류", f"프로젝트를 저장하는 중 오류가 발생했습니다:\n{e}"); return False
            
    def load_state(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f: state_data = json.load(f)
            self.new_project()
            self.is_loading_state = True; self.variable_handler.is_loading = True; self.task_handler.is_loading = True
            for var_data in state_data.get('variables', []):
                if var_data.get('name', '').upper() in BUILT_IN_VARS: continue
                var = Variable(id=var_data.get('id'), name=var_data.get('name'), value=var_data.get('value'))
                if not var.id or not var.name: continue
                self.variables[var.id] = var; item = QListWidgetItem(var.name); item.setData(Qt.UserRole, var.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable); self.var_panel.list_widget.addItem(item)
            for task_data in state_data.get('tasks', []):
                task = Task(id=task_data.get('id'), name=task_data.get('name'), prompt=task_data.get('prompt'), 
                            enabled=task_data.get('enabled', True), output_template=task_data.get('output_template', ''))
                if not task.id or not task.name: continue
                self.tasks[task.id] = task; item = QListWidgetItem(task.name); item.setData(Qt.UserRole, task.id)
                item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if task.enabled else Qt.Unchecked); self.task_panel.list_widget.addItem(item)
            settings = state_data.get('settings', {}); 
            self.run_panel.output_folder_edit.setText(settings.get('output_folder', os.path.join(os.getcwd(), "output_pyside")))
            self.run_panel.output_ext_edit.setText(settings.get('output_extension', '.md'))
            self.run_panel.log_folder_edit.setText(settings.get('log_folder', ''))
            cache_data = settings.get('context_cache')
            if cache_data and cache_data.get('name'):
                combo = self.run_panel.cache_selector_combo; combo.blockSignals(True)
                display_text = f"{cache_data.get('display_name', '...')} ({cache_data.get('model', '...')})"
                if combo.findData(cache_data) == -1: combo.addItem(display_text, cache_data)
                combo.setCurrentIndex(combo.findData(cache_data))
                self.run_panel.model_selector_combo.setCurrentText(cache_data.get('model', ''))
                combo.blockSignals(False)
            else:
                default_model = SUPPORTED_MODELS[0] if SUPPORTED_MODELS else ""
                self.run_panel.model_selector_combo.setCurrentText(settings.get('model_name', default_model))
            self.current_project_path = path; self.is_dirty = False
            self.update_window_title(); self.update_completer_model_and_filter()
            self.log(f"프로젝트 '{os.path.basename(path)}'를 불러왔습니다."); self.refresh_caches()
        except Exception as e:
            self.new_project(); QMessageBox.critical(self, "프로젝트 열기 오류", f"'{os.path.basename(path)}' 파일을 불러오는 중 오류가 발생했습니다:\n{e}")
        finally: 
            self.is_loading_state = False; self.variable_handler.is_loading = False; self.task_handler.is_loading = False
            
    def closeEvent(self, event):
        if self.check_before_proceed("프로그램 종료"): event.accept()
        else: event.ignore()

    def update_completer_model_and_filter(self):
        self.all_vars_model.clear(); valid_var_names = BUILT_IN_VARS.copy()
        for var in self.variables.values(): valid_var_names.add(var.name)
        for var_name in sorted(list(BUILT_IN_VARS)):
            item = QStandardItem(var_name); item.setData(QColor("#4a90e2"), Qt.ForegroundRole)
            item.setToolTip(f"내장 변수: {var_name}"); item.setData('built-in', VAR_TYPE_ROLE); self.all_vars_model.appendRow(item)
        for var in sorted(self.variables.values(), key=lambda v: v.name):
            item = QStandardItem(var.name); item.setData('user', VAR_TYPE_ROLE); self.all_vars_model.appendRow(item)
        self.update_variable_completer_filter()
        for editor in self.highlighter_editors: editor.highlighter.set_valid_variables(valid_var_names)
        
    def update_variable_completer_filter(self):
        current_item = self.var_panel.list_widget.currentItem()
        if current_item: self.variable_proxy_model.set_exclude_name(current_item.text())
        else: self.variable_proxy_model.set_exclude_name("")
        
    @Slot(str)
    def log(self, message): self.run_panel.log_viewer.append(message)
    
    @Slot()
    def clear_log(self): self.run_panel.log_viewer.clear(); self.log("로그가 삭제되었습니다.")
    
    def set_ui_enabled(self, enabled):
        self.var_panel.setEnabled(enabled); self.task_panel.setEnabled(enabled)
        for widget in [self.run_panel.api_key_edit, self.run_panel.output_folder_edit, self.run_panel.select_folder_btn, 
                       self.run_panel.open_output_folder_btn, self.run_panel.output_ext_edit, self.run_panel.log_folder_edit, 
                       self.run_panel.select_log_folder_btn, self.run_panel.open_log_folder_btn, self.run_panel.clear_log_btn, 
                       self.run_panel.cache_selector_combo, self.run_panel.refresh_cache_btn, self.run_panel.model_selector_combo]:
            widget.setEnabled(enabled)
        if enabled: self.run_panel.run_btn.show(); self.run_panel.stop_btn.hide()
        else: self.run_panel.run_btn.hide(); self.run_panel.stop_btn.show()
        if self.run_panel.cache_selector_combo.currentData(): self.run_panel.model_selector_combo.setEnabled(False)
        
    def start_execution(self):
        api_key = self.run_panel.api_key_edit.text()
        if not api_key: QMessageBox.warning(self, "오류", "Gemini API 키를 입력해주세요."); return
        cache_data = self.run_panel.cache_selector_combo.currentData()
        cache_name = cache_data['name'] if cache_data else None
        model_name = self.run_panel.model_selector_combo.currentText()
        tasks_to_run = [self.tasks[self.task_panel.list_widget.item(i).data(Qt.UserRole)] 
                        for i in range(self.task_panel.list_widget.count()) if self.task_panel.list_widget.item(i).checkState() == Qt.Checked]
        if not tasks_to_run: QMessageBox.warning(self, "오류", "실행할 활성화된 태스크가 없습니다."); return
        self.set_ui_enabled(False)
        self.current_runner = TaskRunner(api_key=api_key, model_name=model_name, variables=self.variables, 
                                       tasks_in_order=tasks_to_run, output_folder=self.run_panel.output_folder_edit.text(),
                                       output_extension=self.run_panel.output_ext_edit.text(), log_folder=self.run_panel.log_folder_edit.text(),
                                       cached_content_name=cache_name)
        self.current_runner.signals.log_message.connect(self.log)
        self.current_runner.signals.error.connect(lambda e: QMessageBox.critical(self, "실행 오류", str(e)))
        self.current_runner.signals.finished.connect(self.on_execution_finished); self.thread_pool.start(self.current_runner)
        
    def stop_execution(self):
        if self.current_runner: self.log("사용자 중지 요청..."); self.current_runner.stop()
        
    def on_execution_finished(self): self.set_ui_enabled(True); self.current_runner = None
    
    def select_folder_for(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택");
        if folder: line_edit.setText(folder); self.mark_as_dirty()
        
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