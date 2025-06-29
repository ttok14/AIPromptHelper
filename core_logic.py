# core_logic.py

import google.generativeai as genai
import os
import re
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QRunnable, Slot

class VariableResolver:
    # *** 수정됨: 내장 변수 우선순위 및 컨텍스트 변수 처리 로직 추가 ***
    def __init__(self, variables):
        # 사용자 정의 변수
        self.variables = {var.name: var.value for var in variables.values()}
        self.var_pattern = re.compile(r"\{(.+?)\}")

    def resolve(self, text, context_vars=None, visited=None):
        if visited is None: visited = set()
        if context_vars is None: context_vars = {}
        
        if len(visited) > len(self.variables) + len(context_vars):
             raise ValueError(f"변수 참조 깊이가 너무 깊습니다. 순환 참조 가능성: {' -> '.join(list(visited))}")

        resolved_text = text
        # finditer는 순차적으로 찾으므로, 뒤에서부터 치환해야 인덱스가 깨지지 않음
        for match in reversed(list(self.var_pattern.finditer(text))):
            var_name = match.group(1)
            
            if var_name in visited:
                raise ValueError(f"순환 변수 참조 오류: {' -> '.join(list(visited))} -> {var_name}")

            # 변수 값 찾기 (우선순위: 컨텍스트 변수 > 사용자 정의 변수)
            resolved_value = None
            if var_name in context_vars:
                # 컨텍스트 변수({RESPONSE})는 다른 변수를 참조할 수 없으므로 바로 값 사용
                resolved_value = context_vars[var_name]
            elif var_name in self.variables:
                new_visited = visited.copy()
                new_visited.add(var_name)
                # 사용자 변수는 재귀적으로 해석
                resolved_value = self.resolve(self.variables[var_name], context_vars, new_visited)
            
            if resolved_value is not None:
                start, end = match.span()
                resolved_text = resolved_text[:start] + resolved_value + resolved_text[end:]
                
        return resolved_text

class TaskRunnerSignals(QObject):
    log_message = Signal(str)
    finished = Signal()
    error = Signal(str)

class TaskRunner(QRunnable):
    def __init__(self, api_key, model_name, variables, tasks_in_order, output_folder, output_extension, log_folder):
        super().__init__()
        self.signals = TaskRunnerSignals()
        self.api_key = api_key
        self.model_name = model_name
        self.variables = variables
        self.tasks_in_order = tasks_in_order
        self.output_folder = output_folder
        self.output_extension = output_extension
        self.log_folder = log_folder
        self.is_running = True
        self.log_filepath = None

    def _file_log(self, message):
        if not self.log_folder: return
        if not self.log_filepath:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.log_filepath = os.path.join(self.log_folder, f"log_{timestamp}.txt")
            try: os.makedirs(self.log_folder, exist_ok=True)
            except OSError as e:
                self.signals.log_message.emit(f"로그 폴더 생성 실패: {e}"); self.log_folder = None; return
        with open(self.log_filepath, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S')} - {message}\n")

    def _log(self, message):
        self.signals.log_message.emit(message)
        self._file_log(message)

    @Slot()
    def run(self):
        self._log("="*40); self._log("🚀 워크플로우 실행을 시작합니다.")
        try:
            resolver = VariableResolver(self.variables)
            genai.configure(api_key=self.api_key)
            self._log(f"🧠 사용할 모델: {self.model_name}")
            model = genai.GenerativeModel(self.model_name)
            os.makedirs(self.output_folder, exist_ok=True)
            self._log(f"📂 결과 저장 폴더: {self.output_folder}")

            for task in self.tasks_in_order:
                if not self.is_running: self._log("🔴 작업이 사용자에 의해 중단되었습니다."); break
                
                resolved_task_name = resolver.resolve(task.name)
                self._log(f"\n▶ 태스크 '{task.name}' (-> '{resolved_task_name}') 실행 시작...")
                
                final_prompt = resolver.resolve(task.prompt)
                self._log("  - 프롬프트 생성 완료. API 요청 중...")
                
                response = model.generate_content(final_prompt)
                response_text = response.text
                self._log("  - API 응답 수신 완료.")

                # *** 수정됨: 저장 내용 템플릿 처리 로직 추가 ***
                # 1. 출력 템플릿을 가져옴. 비어있으면 {RESPONSE}를 기본값으로 사용
                output_template = task.output_template if task.output_template.strip() else "{RESPONSE}"
                
                # 2. {RESPONSE}를 포함하는 컨텍스트 변수 생성
                context_vars = {"RESPONSE": response_text}
                
                # 3. 컨텍스트 변수를 이용해 최종 저장 내용 해석
                final_output_content = resolver.resolve(output_template, context_vars)

                safe_task_name = "".join(c if c.isalnum() or c in ' -_' else '_' for c in resolved_task_name)
                ext = self.output_extension if self.output_extension.startswith('.') else '.' + self.output_extension
                filepath = os.path.join(self.output_folder, f"{safe_task_name}{ext}")
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(final_output_content) # 최종 해석된 내용 저장
                
                self._log(f"✅ 파일 저장 완료: {filepath}")

        except Exception as e:
            error_msg = f"❌ 치명적인 오류 발생: {type(e).__name__}: {e}"
            self._log(error_msg)
            self.signals.error.emit(error_msg)
        finally:
            if self.is_running: self._log("\n🎉 모든 작업이 완료되었습니다.")
            self._log("="*40)
            self.signals.finished.emit()
            
    def stop(self):
        self.is_running = False