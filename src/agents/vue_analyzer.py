"""Vue 파일 분석기 - Vue 컴포넌트 구조 및 Best Practices 분석"""

import json
import tempfile
import subprocess
import os
import logging
import re
from typing import List, Dict, Any
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueSeverity, IssueType


class VueAnalyzer(BaseAnalyzer):
    """Vue 파일 분석기"""
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.vue_parser_available = self._check_vue_parser()
    
    def _check_vue_parser(self) -> bool:
        """Vue 파서 사용 가능 여부 확인"""
        try:
            # @vue/compiler-sfc가 설치되어 있는지 확인
            subprocess.run(['node', '-e', 'require("@vue/compiler-sfc")'], 
                         capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.logger.warning("Vue 파서를 찾을 수 없습니다. 기본 분석기로 대체합니다.")
            return False
    
    def analyze_code(self, code: str, file_path: str, diff_content: str = "") -> Dict[str, Any]:
        """Vue 코드 분석"""
        self._clear_results()
        
        try:
            # 항상 ESLint 기반 분석 사용
            self._analyze_with_eslint(code, file_path, diff_content)
            
            # 공통 메트릭스 계산
            self._calculate_metrics(code, file_path)
            
        except Exception as e:
            self.logger.error(f"Vue 분석 중 오류 발생: {e}")
            # 기본 이슈 추가
            self.issues.append(CodeIssue(
                type=IssueType.BUG_RISK,
                severity=IssueSeverity.HIGH,
                message=f"Vue 분석 실패: {str(e)}",
                file_path=file_path,
                line_number=1
            ))
        
        return {
            'issues': self.issues,
            'metrics': self.metrics,
            'summary': self._generate_summary()
        }
    
    def _analyze_with_vue_parser(self, code: str, file_path: str, diff_content: str = "") -> None:
        """Vue 파서를 사용한 분석"""
        try:
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.vue', delete=False) as f:
                f.write(code)
                temp_file_path = f.name
            
            try:
                # Vue 컴파일러를 사용하여 분석
                node_script = f"""
                const compiler = require('@vue/compiler-sfc');
                const fs = require('fs');
                
                const source = fs.readFileSync('{temp_file_path}', 'utf8');
                const parsed = compiler.parse(source);
                
                if (parsed.errors && parsed.errors.length > 0) {{
                    console.log(JSON.stringify({{errors: parsed.errors}}));
                }} else {{
                    const descriptor = parsed.descriptor;
                    const result = {{
                        template: descriptor.template ? {{lang: descriptor.template.lang}} : null,
                        script: descriptor.script ? {{lang: descriptor.script.lang}} : null,
                        scriptSetup: descriptor.scriptSetup ? {{lang: descriptor.scriptSetup.lang}} : null,
                        styles: descriptor.styles ? descriptor.styles.map(s => ({{lang: s.lang, scoped: s.scoped}})) : [],
                        customBlocks: descriptor.customBlocks ? descriptor.customBlocks.length : 0
                    }};
                    console.log(JSON.stringify(result));
                }}
                """
                
                result = subprocess.run(
                    ['node', '-e', node_script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0 and result.stdout:
                    vue_info = json.loads(result.stdout)
                    
                    # 에러 처리
                    if 'errors' in vue_info:
                        for error in vue_info['errors']:
                            line_number = error.get('loc', {}).get('start', {}).get('line', 1)
                            # diff 기반 필터링
                            if not diff_content or self._is_line_in_diff(diff_content, line_number):
                                self.issues.append(CodeIssue(
                                    type=IssueType.SYNTAX_ERROR,
                                    severity=IssueSeverity.HIGH,
                                    message=f"Vue 파싱 오류: {error.get('message', '알 수 없는 오류')}",
                                    file_path=file_path,
                                    line_number=line_number
                                ))
                    else:
                        # Vue 구조 분석
                        self._analyze_vue_structure(vue_info, file_path, diff_content)
                
            finally:
                # 임시 파일 삭제
                os.unlink(temp_file_path)
                
        except subprocess.TimeoutExpired:
            self.logger.warning("Vue 파서 분석 시간 초과")
            self.issues.append(CodeIssue(
                type=IssueType.PERFORMANCE,
                severity=IssueSeverity.MEDIUM,
                message="Vue 컴포넌트 분석 시간이 너무 오래 걸립니다",
                file_path=file_path
            ))
        except Exception as e:
            self.logger.warning(f"Vue 파서 분석 실패, ESLint로 대체: {e}")
            self._analyze_with_eslint(code, file_path, diff_content)
    
    def _analyze_vue_structure(self, vue_info: Dict[str, Any], file_path: str, diff_content: str = "") -> None:
        """Vue 컴포넌트 구조 분석"""
        # 템플릿 분석
        if vue_info.get('template'):
            template_lang = vue_info['template'].get('lang')
            if template_lang and template_lang != 'html':
                self.issues.append(CodeIssue(
                    type=IssueType.STYLE,
                    severity=IssueSeverity.LOW,
                    message=f"템플릿 언어가 표준 HTML이 아닙니다: {template_lang}",
                    file_path=file_path
                ))
        
        # 스크립트 분석
        script_info = vue_info.get('script') or vue_info.get('scriptSetup')
        if script_info:
            script_lang = script_info.get('lang')
            if script_lang and script_lang not in ['js', 'ts']:
                self.issues.append(CodeIssue(
                    type=IssueType.STYLE,
                    severity=IssueSeverity.LOW,
                    message=f"스크립트 언어가 표준 JavaScript/TypeScript가 아닙니다: {script_lang}",
                    file_path=file_path
                ))
        
        # 스타일 분석
        styles = vue_info.get('styles', [])
        if len(styles) > 2:
            self.issues.append(CodeIssue(
                type=IssueType.MAINTAINABILITY,
                severity=IssueSeverity.LOW,
                message=f"스타일 블록이 너무 많습니다 ({len(styles)}개). 분리하는 것을 고려하세요.",
                file_path=file_path
            ))
        
        for i, style in enumerate(styles):
            if style.get('lang') and style['lang'] not in ['css', 'scss', 'sass', 'less', 'stylus']:
                self.issues.append(CodeIssue(
                    type=IssueType.STYLE,
                    severity=IssueSeverity.LOW,
                    message=f"스타일 블록 {i+1}의 언어가 표준 CSS가 아닙니다: {style['lang']}",
                    file_path=file_path
                ))
            
            # scoped CSS 권장
            if not style.get('scoped'):
                self.issues.append(CodeIssue(
                    type=IssueType.BEST_PRACTICES,
                    severity=IssueSeverity.LOW,
                    message=f"스타일 블록 {i+1}에 scoped 속성이 없습니다. 스타일 충돌을 방지하기 위해 scoped를 사용하세요.",
                    file_path=file_path
                ))
        
        # 커스텀 블록 분석
        custom_blocks = vue_info.get('customBlocks', 0)
        if custom_blocks > 0:
            self.issues.append(CodeIssue(
                type=IssueType.BEST_PRACTICES,
                severity=IssueSeverity.LOW,
                message=f"커스텀 블록이 {custom_blocks}개 발견되었습니다. 표준적인 사용인지 확인하세요.",
                file_path=file_path
            ))
    
    def _analyze_with_eslint(self, code: str, file_path: str, diff_content: str = "") -> None:
        """ESLint를 사용한 Vue 분석"""
        try:
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.vue', delete=False) as f:
                f.write(code)
                temp_file_path = f.name
            
            try:
                # ESLint 실행
                cmd = [
                    'npx', 'eslint',
                    temp_file_path,
                    '--config', 'eslint.config.js',
                    '--format', 'json',
                    '--no-ignore',
                    '--no-warn-ignored'
                ]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                
                if result.returncode in [0, 1] and result.stdout:  # 0: no issues, 1: issues found
                    eslint_results = json.loads(result.stdout)
                    self._convert_eslint_issues(eslint_results, file_path, diff_content)
                elif result.returncode not in [0, 1]:
                    self.logger.warning(f"ESLint 실행 실패: {result.stderr}")
                    self.issues.append(CodeIssue(
                        type=IssueType.TOOL_ISSUE,
                        severity=IssueSeverity.MEDIUM,
                        message="Vue 파일 분석 도구 실행 실패",
                        file_path=file_path
                    ))
                    
            finally:
                # 임시 파일 삭제
                os.unlink(temp_file_path)
                
        except subprocess.TimeoutExpired:
            self.logger.warning("ESLint 분석 시간 초과")
            self.issues.append(CodeIssue(
                type=IssueType.PERFORMANCE,
                severity=IssueSeverity.MEDIUM,
                message="Vue 컴포넌트 ESLint 분석 시간 초과",
                file_path=file_path
            ))
        except json.JSONDecodeError:
            self.logger.error("ESLint 결과 파싱 실패")
        except Exception as e:
            self.logger.error(f"ESLint 분석 중 오류: {e}")
        
        # Vue 특화 분석 규칙 적용
        self._analyze_vue_best_practices(code, file_path, diff_content)
    
    def _analyze_vue_best_practices(self, code: str, file_path: str, diff_content: str = "") -> None:
        """Vue Best Practices 분석"""
        lines = code.splitlines()
        
        # 컴포넌트 이름 규칙 검사
        component_name_pattern = r'name:\s*[\'"]([a-zA-Z]+)[\'"]'
        import re
        component_name_match = re.search(component_name_pattern, code)
        if component_name_match:
            component_name = component_name_match.group(1)
            if not re.match(r'^[A-Z][a-zA-Z]*$', component_name):
                # diff 기반 필터링
                if not diff_content or self._is_line_in_diff(diff_content, 1):  # 컴포넌트 이름은 일반적으로 파일 상단에 위치
                    self.issues.append(CodeIssue(
                        type=IssueType.BEST_PRACTICES,
                        severity=IssueSeverity.LOW,
                        message=f"컴포넌트 이름 '{component_name}'은 PascalCase를 사용하는 것을 권장합니다.",
                        file_path=file_path
                    ))
        
        # v-for와 key 사용 검사
        for i, line in enumerate(lines, 1):
            if 'v-for' in line and ':key' not in line and 'v-bind:key' not in line:
                # diff 기반 필터링
                if not diff_content or self._is_line_in_diff(diff_content, i):
                    self.issues.append(CodeIssue(
                        type=IssueType.BUG_RISK,
                        severity=IssueSeverity.HIGH,
                        message="v-for 디렉티브에는 key 속성이 반드시 필요합니다. 렌더링 성능과 상태 관리를 위해 key를 반드시 지정하세요.",
                        file_path=file_path,
                        line_number=i
                    ))
        
        # 사용되지 않는 변수 검사
        unused_var_pattern = r'const\s+(\w+)\s*=\s*[^;]+'
        for i, line in enumerate(lines, 1):
            match = re.search(unused_var_pattern, line)
            if match:
                var_name = match.group(1)
                # 변수가 코드에서 사용되는지 확인 (간단한 검사)
                if var_name != 'unusedVar':  # 실제 구현에서는 더 정교한 검사 필요
                    pass
                else:
                    # diff 기반 필터링
                    if not diff_content or self._is_line_in_diff(diff_content, i):
                        self.issues.append(CodeIssue(
                            type=IssueType.BEST_PRACTICES,
                            severity=IssueSeverity.LOW,
                            message=f"변수 '{var_name}'이 선언되었지만 사용되지 않습니다.",
                            file_path=file_path,
                            line_number=i
                        ))
        
        # 중복 스타일 규칙 검사
        style_blocks = []
        in_style_block = False
        current_style_content = []
        
        for i, line in enumerate(lines, 1):
            if '<style' in line:
                in_style_block = True
                current_style_content = [line]
            elif '</style>' in line and in_style_block:
                current_style_content.append(line)
                style_blocks.append((current_style_content, i - len(current_style_content) + 1))
                in_style_block = False
            elif in_style_block:
                current_style_content.append(line)
        
        # 중복 선택자 검사 (개선된 구현)
        style_selectors = {}
        for style_content, start_line in style_blocks:
            style_text = '\n'.join(style_content)
            # CSS 선택자만 추출 (태그 이름 제외)
            selector_pattern = r'([.#][\w-]+|\w+(?=\s*\{))'
            selectors = re.findall(selector_pattern, style_text)
            for selector in selectors:
                if selector in style_selectors:
                    # diff 기반 필터링 - 스타일 블록의 시작 라인 기준
                    if not diff_content or self._is_line_in_diff(diff_content, start_line):
                        self.issues.append(CodeIssue(
                            type=IssueType.MAINTAINABILITY,
                            severity=IssueSeverity.LOW,
                            message=f"선택자 '{selector}'가 여러 스타일 블록에서 중복 정의되었습니다.",
                            file_path=file_path,
                            line_number=start_line
                        ))
                else:
                    style_selectors[selector] = True
        
        # scoped CSS 권장 (스타일 블록의 시작 라인 기준)
        for style_content, start_line in style_blocks:
            style_text = '\n'.join(style_content)
            if 'scoped' not in style_text:
                # diff 기반 필터링 - 스타일 블록의 시작 라인 기준
                if not diff_content or self._is_line_in_diff(diff_content, start_line):
                    self.issues.append(CodeIssue(
                        type=IssueType.BEST_PRACTICES,
                        severity=IssueSeverity.LOW,
                        message=f"스타일 블록에 scoped 속성이 없습니다. 스타일 충돌을 방지하기 위해 scoped를 사용하세요.",
                        file_path=file_path,
                        line_number=start_line
                    ))
    
    def _convert_eslint_issues(self, eslint_results: List[Dict], file_path: str, diff_content: str = "") -> None:
        """ESLint 이슈를 CodeIssue로 변환"""
        for result in eslint_results:
            if 'messages' not in result:
                continue
                
            for message in result['messages']:
                line_number = message.get('line', 1)
                # diff 기반 필터링
                if not diff_content or self._is_line_in_diff(diff_content, line_number):
                    # Vue 관련 규칙 매핑
                    rule_id = message.get('ruleId', '')
                    issue_type = self._map_eslint_rule_to_issue_type(rule_id)
                    
                    # 심각도 매핑
                    severity = self._map_eslint_severity(message.get('severity', 1))
                    
                    self.issues.append(CodeIssue(
                        type=issue_type,
                        severity=severity,
                        message=f"{message.get('message', '알 수 없는 문제')}",
                        file_path=file_path,
                        line_number=message.get('line'),
                        column_number=message.get('column'),
                        end_line=message.get('endLine'),
                        end_column=message.get('endColumn'),
                        rule_reference=f"ESLint Rule: {rule_id}" if rule_id else None
                    ))
    
    def _map_eslint_rule_to_issue_type(self, rule_id: str) -> IssueType:
        """ESLint 규칙 ID를 IssueType으로 매핑"""
        vue_rules = {
            'vue/no-unused-vars': IssueType.BEST_PRACTICES,
            'vue/no-unused-components': IssueType.BEST_PRACTICES,
            'vue/require-v-for-key': IssueType.BUG_RISK,
            'vue/require-default-prop': IssueType.BEST_PRACTICES,
            'vue/no-v-html': IssueType.SECURITY,
            'vue/order-in-components': IssueType.STYLE,
            'vue/multi-word-component-names': IssueType.STYLE,
            'vue/valid-v-for': IssueType.BUG_RISK,
            'vue/valid-v-if': IssueType.BUG_RISK,
        }
        
        return vue_rules.get(rule_id, IssueType.STYLE)
    
    def _is_line_in_diff(self, diff_content: str, line_number: int) -> bool:
        """Check if a line number is part of the diff content.
        
        Args:
            diff_content: Git diff content
            line_number: Line number to check
            
        Returns:
            True if line is in diff, False otherwise
        """
        if not diff_content or line_number <= 0:
            return True  # If no diff or invalid line number, include all issues
            
        try:
            diff_lines = diff_content.split('\n')
            current_line = 0
            
            for line in diff_lines:
                if line.startswith('@@'):
                    # hunk header: @@ -old_start,old_count +new_start,new_count @@
                    # 예: @@ -1,7 +1,7 @@
                    hunk_match = re.match(r'@@ -\d+,\d+ \+(\d+),(\d+) @@', line)
                    if hunk_match:
                        new_start = int(hunk_match.group(1))
                        new_count = int(hunk_match.group(2))
                        current_line = new_start - 1
                elif line.startswith(' ') or line.startswith('+'):
                    # unchanged or added line
                    current_line += 1
                    if current_line == line_number:
                        return True
                elif line.startswith('-'):
                    # deleted line - skip
                    pass
                else:
                    # context line
                    current_line += 1
                    if current_line == line_number:
                        return True
                        
            return False
        except Exception as e:
            self.logger.warning(f"Failed to check line in diff: {e}")
            return True  # Include issue if diff check fails
    
    def _map_eslint_severity(self, eslint_severity: int) -> IssueSeverity:
        """ESLint 심각도를 IssueSeverity로 매핑"""
        severity_map = {
            1: IssueSeverity.LOW,    # warning
            2: IssueSeverity.MEDIUM  # error
        }
        return severity_map.get(eslint_severity, IssueSeverity.LOW)
    
    def _calculate_metrics(self, code: str, file_path: str) -> None:
        """Vue 파일 메트릭스 계산"""
        lines = code.splitlines()
        self.metrics['total_lines'] = len(lines)
        self.metrics['non_empty_lines'] = len([line for line in lines if line.strip()])
        self.metrics['comment_lines'] = len([line for line in lines if line.strip().startswith('<!--') or line.strip().startswith('//')])
        
        # Vue 특화 메트릭스
        self.metrics['template_lines'] = len([line for line in lines if '<template' in line or '</template>' in line])
        self.metrics['script_lines'] = len([line for line in lines if '<script' in line or '</script>' in line])
        self.metrics['style_lines'] = len([line for line in lines if '<style' in line or '</style>' in line])
        self.metrics['component_count'] = len([line for line in lines if 'export default' in line])
