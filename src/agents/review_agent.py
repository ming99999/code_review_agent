"""Main review agent using LangChain/LangGraph."""
import re
import os
import json
import logging
import ast
import yaml

from typing import Dict, List, Any, Optional, TypedDict
from typing_extensions import Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from models.custom_openai import CodeReviewChatOpenAI
from agents.code_analyzer import CodeAnalyzer, CodeIssue


logger = logging.getLogger(__name__)

config_prompts = {}
try: 
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    config_path = os.path.join(os.path.dirname(parent_dir), 'config', 'prompts.yaml')
    print(f"DEBUG: config path : {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config_prompts = yaml.safe_load(f)
except Exception as e:
    logger.error(f"Failed to load config_prompts: {e}")


class ReviewState(TypedDict):
    """State for the review workflow."""
    diff_content: Annotated[str, lambda x, y: y if y else x]
    file_path: Annotated[str, lambda x, y: y if y else x]
    code_content: Annotated[str, lambda x, y: y if y else x]
    analysis_results: Annotated[Dict[str, Any], lambda x, y: y if y else x]
    style_review_comments: Annotated[List[str], lambda x, y: y if y else x]
    performance_review_comments: Annotated[List[str], lambda x, y: y if y else x]
    maintainability_review_comments: Annotated[List[str], lambda x, y: y if y else x]
    security_review_comments: Annotated[List[str], lambda x, y: y if y else x]
    final_review: Annotated[str, lambda x, y: y if y else x]
    review_config: Annotated[Dict[str, Any], lambda x, y: y if y else x]


class CodeReviewAgent:
    """Main code review agent using LangGraph."""
    
    def __init__(
        self,
        model_name: str = "gpt-4o",
        review_style: str = "comprehensive",
        include_examples: bool = True
    ):
        """Initialize the code review agent.
        
        Args:
            model_name: OpenAI model to use
            review_style: Style of review ('comprehensive', 'focused', 'minimal')
            include_examples: Whether to include code examples
        """
        self.llm = CodeReviewChatOpenAI(
            model_name=model_name,
            temperature=0.1,
            review_style=review_style,
            include_code_examples=include_examples
        )
        self.analyzer = CodeAnalyzer()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the review workflow graph."""
        
        def analyze_code(state: ReviewState) -> ReviewState:
            """Analyze code for issues."""
            logger.info(f"Analyzing code in {state['file_path']}")
            
            analysis = self.analyzer.analyze_code(
                state['code_content'], 
                state['file_path']
            )
            
            state['analysis_results'] = analysis
            return state
        
        def generate_style_review(state: ReviewState) -> ReviewState:
            """Generate style-related review comments."""
            # 안전하게 issues 접근
            analysis_results = state.get('analysis_results', {})
            issues = analysis_results.get('issues', []) if isinstance(analysis_results, dict) else []
            
            style_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'style'
            ]
            
            if style_issues:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a Python style expert. 
                    Review the following style issues and provide constructive feedback.
                    Focus on PEP 8 compliance and code readability.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {state['file_path']}
Style Issues Found:
{self._format_issues(style_issues)}

Code Snippet:
```python
{state['code_content'][:1000]}...
```

Provide specific, actionable feedback for each style issue in Korean.
Keep it brief and focused on the most important issues.
""")
                ])
                
                try:
                    response = self.llm.invoke(prompt.format_messages())
                    if response and hasattr(response, 'content'):
                        content = response.content.strip()
                        if content:
                            state['style_review_comments'] = [f"**스타일 리뷰**\n{content}"]
                        else:
                            state['style_review_comments'] = ["**스타일 리뷰**\n스타일 관련 이슈가 발견되지 않았습니다."]
                    else:
                        state['style_review_comments'] = ["**스타일 리뷰**\n스타일 관련 이슈가 발견되지 않았습니다."]
                except Exception as e:
                    state['style_review_comments'] = [f"**스타일 리뷰**\n스타일 리뷰 생성 중 오류 발생: {str(e)}"]
            
            return state
        
        def generate_performance_review(state: ReviewState) -> ReviewState:
            """Generate performance-related review comments."""
            # 안전하게 issues 접근
            analysis_results = state.get('analysis_results', {})
            issues = analysis_results.get('issues', []) if isinstance(analysis_results, dict) else []
            
            performance_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'performance'
            ]
            
            # Also check for performance patterns in the code
            performance_suggestions = self._check_performance_patterns(state['code_content'])
            
            if performance_issues or performance_suggestions:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a Python performance optimization expert.
                    Review the code for performance issues and suggest improvements.
                    Focus on algorithmic efficiency and Python-specific optimizations.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {state['file_path']}
Performance Issues: {len(performance_issues)}
Performance Suggestions: {len(performance_suggestions)}

Code:
```python
{state['code_content'][:1000]}...
```

Provide specific performance improvements with code examples in Korean.
Keep it brief and focused on the most critical issues.
""")
                ])
                
                try:
                    response = self.llm.invoke(prompt.format_messages())
                    if response and hasattr(response, 'content'):
                        content = response.content.strip()
                        if content:
                            state['performance_review_comments'] = [f"**성능 리뷰**\n{content}"]
                        else:
                            state['performance_review_comments'] = ["**성능 리뷰**\n성능 관련 이슈가 발견되지 않았습니다."]
                    else:
                        state['performance_review_comments'] = ["**성능 리뷰**\n성능 관련 이슈가 발견되지 않았습니다."]
                except Exception as e:
                    state['performance_review_comments'] = [f"**성능 리뷰**\n성능 리뷰 생성 중 오류 발생: {str(e)}"]
            
            return state
        
        def generate_maintainability_review(state: ReviewState) -> ReviewState:
            """Generate maintainability review comments."""
            # 안전하게 issues 접근
            analysis_results = state.get('analysis_results', {})
            issues = analysis_results.get('issues', []) if isinstance(analysis_results, dict) else []
            
            maintainability_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value in ['maintainability', 'complexity']
            ]
            
            if maintainability_issues:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a software architecture expert.
                    Review the code for maintainability and clean code principles.
                    Focus on code organization, complexity, and long-term maintainability.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {state['file_path']}
Maintainability Issues: {len(maintainability_issues)}

Code:
```python
{state['code_content'][:1000]}...
```

Provide suggestions for improving code maintainability in Korean.
Keep it brief and focused on the most important issues.
""")
                ])
                
                try:
                    response = self.llm.invoke(prompt.format_messages())
                    if response and hasattr(response, 'content'):
                        content = response.content.strip()
                        if content:
                            state['maintainability_review_comments'] = [f"**유지보수성 리뷰**\n{content}"]
                        else:
                            state['maintainability_review_comments'] = ["**유지보수성 리뷰**\n유지보수성 관련 이슈가 발견되지 않았습니다."]
                    else:
                        state['maintainability_review_comments'] = ["**유지보수성 리뷰**\n유지보수성 관련 이슈가 발견되지 않았습니다."]
                except Exception as e:
                    state['maintainability_review_comments'] = [f"**유지보수성 리뷰**\n유지보수성 리뷰 생성 중 오류 발생: {str(e)}"]
            
            return state
        
        def generate_security_review(state: ReviewState) -> ReviewState:
            """Generate security review comments."""
            # 안전하게 issues 접근
            analysis_results = state.get('analysis_results', {})
            issues = analysis_results.get('issues', []) if isinstance(analysis_results, dict) else []
            
            security_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'security'
            ]
            
            # Check for security patterns
            security_concerns = self._check_security_patterns(state['code_content'])
            
            if security_issues or security_concerns:
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a security expert.
                    Review the code for security vulnerabilities and suggest improvements.
                    Focus on common Python security issues and best practices.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {state['file_path']}
Security Issues: {len(security_issues)}
Security Concerns: {len(security_concerns)}

Code:
```python
{state['code_content'][:1000]}...
```

Identify security vulnerabilities and provide secure alternatives in Korean.
Keep it brief and focused on the most critical issues.
""")
                ])
                
                try:
                    response = self.llm.invoke(prompt.format_messages())
                    if response and hasattr(response, 'content'):
                        content = response.content.strip()
                        if content:
                            state['security_review_comments'] = [f"**보안 리뷰**\n{content}"]
                        else:
                            state['security_review_comments'] = ["**보안 리뷰**\n보안 관련 이슈가 발견되지 않았습니다."]
                    else:
                        state['security_review_comments'] = ["**보안 리뷰**\n보안 관련 이슈가 발견되지 않았습니다."]
                except Exception as e:
                    state['security_review_comments'] = [f"**보안 리뷰**\n보안 리뷰 생성 중 오류 발생: {str(e)}"]
            
            return state
        
        def compile_final_review(state: ReviewState) -> ReviewState:
            """Compile all reviews into final output."""
            
            # 안전하게 analysis_results 접근
            analysis_results = state.get('analysis_results', {})
            if not isinstance(analysis_results, dict):
                analysis_results = {}
            summary = analysis_results.get('summary', {})
            metrics = analysis_results.get('metrics', {})
            
            # 파일별 리뷰 내용 수집
            file_review_content = ""
            
            # Combine all review comments
            all_review_comments = []
            if state.get('style_review_comments'):
                all_review_comments.extend(state['style_review_comments'])
            if state.get('performance_review_comments'):
                all_review_comments.extend(state['performance_review_comments'])
            if state.get('maintainability_review_comments'):
                all_review_comments.extend(state['maintainability_review_comments'])
            if state.get('security_review_comments'):
                all_review_comments.extend(state['security_review_comments'])
            
            for comment in all_review_comments:
                if comment and comment.strip():  # 빈 댓글 제외
                    file_review_content += f"{comment}\n\n"
            
            # LLM을 통해 통합 요약 생성
            if file_review_content.strip():  # 리뷰 내용이 있는 경우에만 요약 생성
                summary_prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are an expert code review summarizer.
                    Analyze the detailed file reviews and provide a comprehensive summary in Korean.
                    Focus on:
                    1. What was done well (positives)
                    2. Areas needing improvement (issues found)
                    3. Suggestions for growth as a better developer
                    Write in Korean and be constructive and encouraging."""),
                    HumanMessage(content=f"""
File: {state['file_path']}

Detailed Reviews:
{file_review_content}

Analysis Summary:
- Total Issues: {summary.get('total_issues', 0) if isinstance(summary, dict) else 0}
- Critical Issues: {summary.get('critical_issues', 0) if isinstance(summary, dict) else 0}
- High Priority Issues: {summary.get('high_issues', 0) if isinstance(summary, dict) else 0}

Provide a structured summary. no title, only with:
##1. 잘한 점 (Positives)
##2. 개선이 필요한 부분 (Areas for Improvement)  
##3. 좋은 개발자로 성장하기 위한 제안 (Growth Suggestions)
##4. 총평
""")
                ])
                
                try:
                    summary_response = self.llm.invoke(summary_prompt.format_messages())
                    llm_summary = summary_response.content
                except Exception as e:
                    llm_summary = f"요약 생성 중 오류 발생: {str(e)}\n\n{file_review_content}"
            else:
                llm_summary = "상세 리뷰가 생성되지 않았습니다."
            
            # 통합 리뷰 생성
            final_review = f"""## 📝 파일별 코드 리뷰

### 📄 파일 정보
- **파일명**: {state['file_path']}
- **총 라인 수**: {metrics.get('total_lines', 'N/A') if isinstance(metrics, dict) else 'N/A'}
- **함수 수**: {metrics.get('function_count', 'N/A') if isinstance(metrics, dict) else 'N/A'}
- **클래스 수**: {metrics.get('class_count', 'N/A') if isinstance(metrics, dict) else 'N/A'}

### 🔍 파일별 상세 리뷰
{file_review_content if file_review_content.strip() else '상세 리뷰가 없습니다.'}

## 📊 전체 코드 리뷰 요약
{llm_summary}

"""
            
            # Add critical issues warning
            critical_issues = summary.get('critical_issues', 0) if isinstance(summary, dict) else 0
            if critical_issues > 0:
                final_review += """## 🚨 크리티컬 이슈 발견
병합하기 전에 크리티컬 이슈를 반드시 해결해주세요.

"""
            
            state['final_review'] = final_review
            return state
        
        # Build the graph
        workflow = StateGraph(ReviewState)
        
        # Add nodes
        workflow.add_node("analyze", analyze_code)
        workflow.add_node("style_review", generate_style_review)
        workflow.add_node("performance_review", generate_performance_review)
        workflow.add_node("maintainability_review", generate_maintainability_review)
        workflow.add_node("security_review", generate_security_review)
        workflow.add_node("compile_review", compile_final_review)
        
        # Add edges
        workflow.set_entry_point("analyze")
        
        # Run reviews in parallel after analysis
        workflow.add_edge("analyze", "style_review")
        workflow.add_edge("analyze", "performance_review")
        workflow.add_edge("analyze", "maintainability_review")
        workflow.add_edge("analyze", "security_review")
        
        # Compile final review after all reviews are done
        workflow.add_edge("style_review", "compile_review")
        workflow.add_edge("performance_review", "compile_review")
        workflow.add_edge("maintainability_review", "compile_review")
        workflow.add_edge("security_review", "compile_review")
        
        workflow.set_finish_point("compile_review")
        
        # Compile the graph
        return workflow.compile()
    
    def review_code(self, code_content: str, file_path: str, diff_content: str = "") -> str:
        """Review code and return formatted review."""
        
        try:
            # 1. 코드 분석
            logger.info(f"Step 1: Analyzing code in {file_path}")
            analysis_results = self.analyzer.analyze_code(code_content, file_path)
            logger.info(f"Step 1 completed: Analysis done for {file_path}")
            
            # 2. 각 리뷰 카테고리별 리뷰 생성
            style_review = self._generate_style_review(analysis_results, code_content, file_path)
            logger.info(f"Step 2: Style review completed for {file_path}")
            
            performance_review = self._generate_performance_review(analysis_results, code_content, file_path)
            logger.info(f"Step 3: Performance review completed for {file_path}")
            
            maintainability_review = self._generate_maintainability_review(analysis_results, code_content, file_path)
            logger.info(f"Step 4: Maintainability review completed for {file_path}")
            
            security_review = self._generate_security_review(analysis_results, code_content, file_path)
            logger.info(f"Step 5: Security review completed for {file_path}")
            
            # 3. 최종 리뷰 컴파일
            logger.info(f"Step 6: Compiling final review for {file_path}")
            final_review = self._compile_final_review(
                analysis_results, 
                style_review, 
                performance_review, 
                maintainability_review, 
                security_review,
                file_path
            )
            logger.info(f"Step 6 completed: Final review compiled for {file_path}")
            
            return final_review
            
        except Exception as e:
            logger.error(f"Review generation failed for {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return f"Error generating review: {str(e)}"
    
    def _generate_style_review(self, analysis_results: Dict, code_content: str, file_path: str) -> str:
        """Generate style review."""
        try:
            issues = analysis_results.get('issues', [])
            style_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'style'
            ]
            
            if style_issues:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.messages import SystemMessage, HumanMessage
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a Python style expert. 
                    Review the following style issues and provide constructive feedback.
                    Focus on PEP 8 compliance and code readability.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {file_path}
Style Issues Found:
{self._format_issues(style_issues)}

Code Snippet:
```python
{code_content[:1000]}...
```

Provide specific, actionable feedback for each style issue in Korean.
Keep it brief and focused on the most important issues.
""")
                ])
                
                response = self.llm.invoke(prompt.format_messages())
                if response and hasattr(response, 'content'):
                    content = response.content.strip()
                    if content:
                        return f"**스타일 리뷰**\n{content}"
                    else:
                        return "**스타일 리뷰**\n스타일 관련 이슈가 발견되지 않았습니다."
                else:
                    return "**스타일 리뷰**\n스타일 관련 이슈가 발견되지 않았습니다."
            else:
                return "**스타일 리뷰**\n스타일 관련 이슈가 발견되지 않았습니다."
        except Exception as e:
            return f"**스타일 리뷰**\n스타일 리뷰 생성 중 오류 발생: {str(e)}"
    
    def _generate_performance_review(self, analysis_results: Dict, code_content: str, file_path: str) -> str:
        """Generate performance review."""
        try:
            issues = analysis_results.get('issues', [])
            performance_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'performance'
            ]
            
            performance_suggestions = self._check_performance_patterns(code_content)
            
            if performance_issues or performance_suggestions:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.messages import SystemMessage, HumanMessage
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a Python performance optimization expert.
                    Review the code for performance issues and suggest improvements.
                    Focus on algorithmic efficiency and Python-specific optimizations.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {file_path}
Performance Issues: {len(performance_issues)}
Performance Suggestions: {len(performance_suggestions)}

Code:
```python
{code_content[:1000]}...
```

Provide specific performance improvements with code examples in Korean.
Keep it brief and focused on the most critical issues.
""")
                ])
                
                response = self.llm.invoke(prompt.format_messages())
                if response and hasattr(response, 'content'):
                    content = response.content.strip()
                    if content:
                        return f"**성능 리뷰**\n{content}"
                    else:
                        return "**성능 리뷰**\n성능 관련 이슈가 발견되지 않았습니다."
                else:
                    return "**성능 리뷰**\n성능 관련 이슈가 발견되지 않았습니다."
            else:
                return "**성능 리뷰**\n성능 관련 이슈가 발견되지 않았습니다."
        except Exception as e:
            return f"**성능 리뷰**\n성능 리뷰 생성 중 오류 발생: {str(e)}"
    
    def _generate_maintainability_review(self, analysis_results: Dict, code_content: str, file_path: str) -> str:
        """Generate maintainability review."""
        try:
            issues = analysis_results.get('issues', [])
            maintainability_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value in ['maintainability', 'complexity']
            ]
            
            if maintainability_issues:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.messages import SystemMessage, HumanMessage
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a software architecture expert.
                    Review the code for maintainability and clean code principles.
                    Focus on code organization, complexity, and long-term maintainability.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {file_path}
Maintainability Issues: {len(maintainability_issues)}

Code:
```python
{code_content[:1000]}...
```

Provide suggestions for improving code maintainability in Korean.
Keep it brief and focused on the most important issues.
""")
                ])
                
                response = self.llm.invoke(prompt.format_messages())
                if response and hasattr(response, 'content'):
                    content = response.content.strip()
                    if content:
                        return f"**유지보수성 리뷰**\n{content}"
                    else:
                        return "**유지보수성 리뷰**\n유지보수성 관련 이슈가 발견되지 않았습니다."
                else:
                    return "**유지보수성 리뷰**\n유지보수성 관련 이슈가 발견되지 않았습니다."
            else:
                return "**유지보수성 리뷰**\n유지보수성 관련 이슈가 발견되지 않았습니다."
        except Exception as e:
            return f"**유지보수성 리뷰**\n유지보수성 리뷰 생성 중 오류 발생: {str(e)}"
    
    def _generate_security_review(self, analysis_results: Dict, code_content: str, file_path: str) -> str:
        """Generate security review."""
        try:
            issues = analysis_results.get('issues', [])
            security_issues = [
                issue for issue in issues
                if hasattr(issue, 'type') and issue.type.value == 'security'
            ]
            
            security_concerns = self._check_security_patterns(code_content)
            
            if security_issues or security_concerns:
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.messages import SystemMessage, HumanMessage
                
                prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are a security expert.
                    Review the code for security vulnerabilities and suggest improvements.
                    Focus on common Python security issues and best practices.
                    Keep your feedback concise and actionable.
                    Write in Korean."""),
                    HumanMessage(content=f"""
File: {file_path}
Security Issues: {len(security_issues)}
Security Concerns: {len(security_concerns)}

Code:
```python
{code_content[:1000]}...
```

Identify security vulnerabilities and provide secure alternatives in Korean.
Keep it brief and focused on the most critical issues.
""")
                ])
                
                response = self.llm.invoke(prompt.format_messages())
                if response and hasattr(response, 'content'):
                    content = response.content.strip()
                    if content:
                        return f"**보안 리뷰**\n{content}"
                    else:
                        return "**보안 리뷰**\n보안 관련 이슈가 발견되지 않았습니다."
                else:
                    return "**보안 리뷰**\n보안 관련 이슈가 발견되지 않았습니다."
            else:
                return "**보안 리뷰**\n보안 관련 이슈가 발견되지 않았습니다."
        except Exception as e:
            return f"**보안 리뷰**\n보안 리뷰 생성 중 오류 발생: {str(e)}"
    
    def _compile_final_review(self, analysis_results: Dict, style_review: str, performance_review: str, 
                            maintainability_review: str, security_review: str, file_path: str) -> str:
        """Compile all reviews into final output."""
        try:
            summary = analysis_results.get('summary', {})
            metrics = analysis_results.get('metrics', {})
            
            # 파일별 리뷰 내용 수집
            file_review_content = ""
            all_reviews = [style_review, performance_review, maintainability_review, security_review]
            
            for review in all_reviews:
                if review and review.strip():
                    file_review_content += f"{review}\n\n"
            
            # LLM을 통해 통합 요약 생성
            if file_review_content.strip():
                from langchain_core.prompts import ChatPromptTemplate
                from langchain_core.messages import SystemMessage, HumanMessage
                
                summary_prompt = ChatPromptTemplate.from_messages([
                    SystemMessage(content="""You are an expert code review summarizer.
                    Analyze the detailed file reviews and provide a comprehensive summary in Korean.
                    Focus on:
                    1. What was done well (positives)
                    2. Areas needing improvement (issues found)
                    3. Suggestions for growth as a better developer
                    Write in Korean and be constructive and encouraging."""),
                    HumanMessage(content=f"""
File: {file_path}

Detailed Reviews:
{file_review_content}

Analysis Summary:
- Total Issues: {summary.get('total_issues', 0)}
- Critical Issues: {summary.get('critical_issues', 0)}
- High Priority Issues: {summary.get('high_issues', 0)}

Provide a structured summary. no title, only with:
## 1. 잘한 점 (Positives)
## 2. 개선이 필요한 부분 (Areas for Improvement)  
## 3. 좋은 개발자로 성장하기 위한 제안 (Growth Suggestions)
## 4. 총평
""")
                ])
                
                try:
                    summary_response = self.llm.invoke(summary_prompt.format_messages())
                    llm_summary = summary_response.content
                except Exception as e:
                    llm_summary = f"요약 생성 중 오류 발생: {str(e)}\n\n{file_review_content}"
            else:
                llm_summary = "상세 리뷰가 생성되지 않았습니다."
            
            # 통합 리뷰 생성
            final_review = f"""## 📝 파일별 코드 리뷰

### 📄 파일 정보
- **파일명**: {file_path}
- **총 라인 수**: {metrics.get('total_lines', 'N/A')}
- **함수 수**: {metrics.get('function_count', 'N/A')}
- **클래스 수**: {metrics.get('class_count', 'N/A')}

### 🔍 파일별 상세 리뷰
{file_review_content if file_review_content.strip() else '상세 리뷰가 없습니다.'}

## 📊 전체 코드 리뷰 요약
{llm_summary}

"""
            
            # Add critical issues warning
            critical_issues = summary.get('critical_issues', 0)
            if critical_issues > 0:
                final_review += """## 🚨 크리티컬 이슈 발견
병합하기 전에 크리티컬 이슈를 반드시 해결해주세요.

"""
            
            return final_review
            
        except Exception as e:
            logger.error(f"Final review compilation failed: {e}")
            return f"Error compiling final review: {str(e)}"
    
    def _format_issues(self, issues: List[CodeIssue]) -> str:
        """Format issues for prompt."""
        formatted = ""
        for issue in issues[:10]:  # Limit to prevent token overflow
            formatted += f"- Line {issue.line_number}: {issue.message} ({issue.severity.value})\n"
            if issue.suggestion:
                formatted += f"  Suggestion: {issue.suggestion}\n"
        return formatted
    
    def _check_performance_patterns(self, code: str) -> List[str]:
        """Check for performance anti-patterns."""
        patterns = []
        
        # Check for string concatenation in loops
        if re.search(r'for.*in.*:\s*\w+\s*\+=\s*["\']', code):
            patterns.append("String concatenation in loop - use join() instead")
        
        # Check for list comprehension vs loop
        if re.search(r'for.*in.*:\s*\w+\.append\(', code):
            patterns.append("Consider using list comprehension for better performance")
        
        # Check for inefficient imports
        if re.search(r'from\s+\w+\s+import\s+\*', code):
            patterns.append("Wildcard imports can impact performance and namespace")
        
        return patterns
    
    def _check_security_patterns(self, code: str) -> List[str]:
        """Check for security concerns."""
        concerns = []
        
        # Check for hardcoded secrets
        if re.search(r'(password|secret|key|token)\s*=\s*["\'][^"\']+["\']', code, re.IGNORECASE):
            concerns.append("Potential hardcoded secret detected")
        
        # Check for eval usage
        if re.search(r'\beval\s*\(', code):
            concerns.append("Use of eval() is a security risk")
        
        # Check for SQL injection risks
        if re.search(r'execute\s*\(\s*["\'].*\%\s*\w+', code):
            concerns.append("Potential SQL injection vulnerability")
        
        return concerns
    
    def review_pr_files(self, files_data: List[Dict[str, str]]) -> Dict[str, Any]:
        """Review multiple files in a PR and return structured JSON review.
        
        Args:
            files_data: List of dictionaries containing 'file_path' and 'code_content'
            
        Returns:
            Dict with 'summary' and 'comments' for PR review
        """
        try:
            # 1. 각 파일 분석 및 이슈 수집
            all_analysis_results = []
            all_issues = []
            
            # AnalyzerFactory 임포트
            from .analyzer_factory import AnalyzerFactory
            
            for file_data in files_data:
                file_path = file_data.get('file_path', '')
                code_content = file_data.get('code_content', '')
                diff_content = file_data.get('diff_content', '')
                
                if not file_path or not code_content:
                    continue
                    
                # 파일 확장자에 따라 적절한 분석기 사용
                analyzer = AnalyzerFactory.create_analyzer_for_file(file_path, diff_content)
                analysis_results = analyzer.analyze_code(code_content, file_path)
                all_analysis_results.append({
                    'file_path': file_path,
                    'analysis': analysis_results
                })
                
                # 이슈 수집
                issues = analysis_results.get('issues', [])
                all_issues.extend(issues)
            
            # 2. PR 전체 요약 생성
            pr_summary = self._generate_pr_summary(files_data, all_issues)
            
            # 3. 인라인 코멘트 생성
            inline_comments = self._generate_inline_comments(files_data, all_issues)
            
            return {
                'summary': pr_summary,
                'comments': inline_comments
            }
            
        except Exception as e:
            logger.error(f"PR review generation failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'summary': {
                    'summary': f"리뷰 생성 중 오류 발생: {str(e)}",
                    'highlights': [],
                    'top_priorities': [],
                    'growth_suggestions': []
                },
                'comments': []
            }
    
    def _generate_pr_summary(self, files_data: List[Dict[str, str]], all_issues: List[CodeIssue]) -> Dict[str, Any]:
        """Generate PR summary in markdown format."""
        try:
            # 파일 정보 수집
            file_summaries = []
            for file_data in files_data:
                file_path = file_data.get('file_path', '')
                code_content = file_data.get('code_content', '')
                if file_path and code_content:
                    lines = code_content.split('\n')
                    file_summaries.append(f"File: {file_path} ({len(lines)} lines)")
            
            # 이슈 통계
            critical_issues = [issue for issue in all_issues if hasattr(issue, 'severity') and issue.severity.value == 'critical']
            high_issues = [issue for issue in all_issues if hasattr(issue, 'severity') and issue.severity.value == 'high']
            
            # PR 요약 프롬프트 생성
            from langchain_core.prompts import ChatPromptTemplate
            from langchain_core.messages import SystemMessage, HumanMessage
            
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=self._get_pr_summary_prompt()),
                HumanMessage(content=f"""
PR Files:
{chr(10).join(file_summaries)}

Critical Issues: {len(critical_issues)}
High Priority Issues: {len(high_issues)}
Total Issues: {len(all_issues)}

Provide a comprehensive PR review summary in markdown format as specified.
**Write in Korean.**
**IMPORTANT: Respond with ONLY the markdown format. NO additional text, NO explanations.**
""")
            ])
            
            response = self.llm.invoke(prompt.format_messages())
            if response and hasattr(response, 'content'):
                content = response.content.strip()
                
                # 마크다운 응답을 그대로 반환 (JSON 파싱 시도하지 않음)
                if content:
                    return {
                        'positive_feedback': content,
                        'highlights': ['리뷰가 성공적으로 생성되었습니다'],
                        'top_priorities': [f'크리티컬 이슈: {len(critical_issues)}개', f'하이 프라이오리티 이슈: {len(high_issues)}개'],
                        'growth_suggestions': ['코드 품질 개선을 계속 진행해주세요']
                    }
                else:
                    return {
                        'positive_feedback': 'PR 요약을 생성할 수 없습니다',
                        'highlights': [],
                        'top_priorities': [],
                        'growth_suggestions': []
                    }
            else:
                return {
                    'positive_feedback': 'PR 요약을 생성할 수 없습니다',
                    'highlights': [],
                    'top_priorities': [],
                    'growth_suggestions': []
                }
                
        except Exception as e:
            logger.error(f"PR summary generation failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'positive_feedback': f'요약 생성 중 오류 발생: {str(e)}',
                'highlights': [],
                'top_priorities': [],
                'growth_suggestions': []
            }
    
    def _get_pr_summary_prompt(self) -> str:
        """Get PR summary prompt from config."""
        try:
            return config_prompts.get('review_styles', {}).get('pr_markdown', {}).get('system_prompt', '')
        except Exception as e:
            logger.error(f"Failed to load PR markdown prompt: {e}")
            return """You are a senior SW developer and mentor. Provide a comprehensive PR review in markdown format."""
    
    def _generate_inline_comments(self, files_data: List[Dict[str, str]], all_issues: List[CodeIssue]) -> List[Dict[str, Any]]:
        """Generate inline comments for specific issues."""
        comments = []
        
        # critical, high, medium 이슈에 대해서 인라인 코멘트 생성
        important_issues = [
            issue for issue in all_issues 
            if hasattr(issue, 'severity') and issue.severity.value in ['critical', 'high', 'medium']
        ]
        
        for issue in important_issues:
            if not hasattr(issue, 'file_path') or not issue.file_path:
                continue
                
            # line_number가 없으면 1로 설정
            line_number = 1
            if hasattr(issue, 'line_number') and issue.line_number:
                line_number = issue.line_number
            
            comment_body = f"🚨 **{issue.severity.value.upper()}**: {issue.message}"
            
            if hasattr(issue, 'suggestion') and issue.suggestion:
                comment_body += f"\n\n💡 **제안**: {issue.suggestion}"
            
            if hasattr(issue, 'code_example') and issue.code_example:
                comment_body += f"\n\n```python\n{issue.code_example}\n```"
            
            comment = {
                'file_path': issue.file_path,
                'line_number': line_number,
                'body': comment_body,
                'severity': issue.severity.value
            }
            
            comments.append(comment)
        
        return comments
