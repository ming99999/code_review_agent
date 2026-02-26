"""Custom OpenAI Chat Model for Code Review"""

from typing import Any, Dict, List, Optional, Type, Union
from langchain_openai.chat_models.base import BaseChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, AIMessageChunk
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.outputs import ChatResult, ChatGeneration, ChatGenerationChunk
from langchain_core.messages.ai import UsageMetadata
import json
import logging
from .config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL_NAME

logger = logging.getLogger(__name__)


class CodeReviewChatOpenAI(BaseChatOpenAI):
    """Custom ChatOpenAI class optimized for code review tasks with positive tone and Korean support."""
    
    # Review style and localization defaults
    review_style: str = "comprehensive"
    include_code_examples: bool = True
    positive_tone: bool = True
    
    def __init__(
        self,
        *,
        model_name: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = 4096,
        review_style: str = "comprehensive",
        include_code_examples: bool = True,
        positive_tone: bool = True,
        openai_api_key: Optional[str] = None,
        openai_api_base: Optional[str] = None,
        **kwargs: Any,
    ):
        """Initialize CodeReviewChatOpenAI.
        
        Args:
            model_name: OpenAI model name (defaults to OPENAI_MODEL_NAME)
            temperature: Model temperature (0.0-1.0)
            max_tokens: Maximum tokens in response
            review_style: Review style ('comprehensive', 'focused', 'minimal')
            include_code_examples: Whether to include code examples in reviews
            positive_tone: Whether to use positive and encouraging tone
            openai_api_key: API key
            openai_api_base: API base URL
            **kwargs: Additional arguments for BaseChatOpenAI
        """
        model = model_name or OPENAI_MODEL_NAME or "gpt-4o"
        api_key = openai_api_key or OPENAI_API_KEY
        base_url = openai_api_base or OPENAI_API_BASE
        
        super().__init__(
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=api_key,
            base_url=base_url,
            **kwargs
        )
        self.review_style = review_style
        self.include_code_examples = include_code_examples
        self.positive_tone = positive_tone
        
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate response with code review specific handling."""
        
        # Add code review context to system message
        enhanced_messages = self._enhance_messages_with_review_context(messages)
        
        # Generate response using parent class
        response = super()._generate(
            messages=enhanced_messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        )
        
        # Post-process the response for code review format
        processed_response = self._process_review_response(response)
        
        return processed_response
        
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> List[ChatGenerationChunk]:
        """Stream response with code review specific handling."""
        enhanced_messages = self._enhance_messages_with_review_context(messages)
        return super()._stream(enhanced_messages, stop=stop, run_manager=run_manager, **kwargs)

    def _enhance_messages_with_review_context(
        self, 
        messages: List[BaseMessage]
    ) -> List[BaseMessage]:
        """Enhance messages with code review specific context."""
        enhanced_messages = []
        
        for message in messages:
            if isinstance(message, SystemMessage):
                # Add code review specific instructions
                enhanced_content = self._get_code_review_system_prompt()
                if message.content:
                    enhanced_content = f"{message.content}\n\n{enhanced_content}"
                enhanced_messages.append(SystemMessage(content=enhanced_content))
            else:
                enhanced_messages.append(message)
                
        return enhanced_messages
    
    def _get_code_review_system_prompt(self) -> str:
        """Get system prompt for code review tasks, localized in Korean."""
        base_prompt = """You are an expert Python code reviewer with deep knowledge of:
- PEP 8 style guidelines and best practices
- Clean code principles and design patterns
- Performance optimization techniques
- Code maintainability and scalability
- Security best practices
- Software architecture principles

Your role is to provide comprehensive, constructive, and encouraging code reviews that help developers improve their code quality while maintaining a positive and supportive tone.
All responses must be written in Korean.
"""
        
        if self.positive_tone:
            base_prompt += """
**Review Style Guidelines:**
1. Start with positive feedback and what's done well
2. Provide constructive suggestions in a supportive manner
3. Focus on solutions rather than just pointing out problems
4. Use encouraging language throughout the review
5. End with motivational closing remarks
"""
        
        style_prompts = {
            "comprehensive": """Provide detailed analysis covering all aspects of code quality including:
1. Code style and formatting (PEP 8 compliance)
2. Code structure and organization
3. Performance considerations
4. Maintainability and readability
5. Potential bugs or issues
6. Security concerns
7. Suggestions for improvement with code examples
Keep feedback concise and actionable.""",
            "focused": """Focus on the most critical issues:
1. Major code smells or anti-patterns
2. Performance bottlenecks
3. Security vulnerabilities
4. Key improvement suggestions
Keep feedback brief and focused.""",
            "minimal": """Provide concise feedback on:
1. Critical issues only
2. Essential improvements
Keep it very brief."""
        }
        
        format_prompt = """
Format your review as structured feedback with:
- Clear section headers using markdown
- Specific line references when applicable
- Code examples for suggestions (when requested)
- Severity levels (Critical, High, Medium, Low)
- Actionable recommendations
- Write everything in Korean
"""
        
        return f"{base_prompt}\n{style_prompts.get(self.review_style, style_prompts['comprehensive'])}\n{format_prompt}"
    
    def _process_review_response(self, response: ChatResult) -> ChatResult:
        """Process and format the review response."""
        if not response.generations:
            return response
            
        processed_generations = []
        
        for generation in response.generations:
            if isinstance(generation, ChatGeneration):
                processed_message = self._format_review_content(generation.message)
                processed_generation = ChatGeneration(
                    message=processed_message,
                    generation_info=generation.generation_info
                )
                processed_generations.append(processed_generation)
            else:
                processed_generations.append(generation)
                
        return ChatResult(
            generations=processed_generations,
            llm_output=response.llm_output
        )
    
    def _format_review_content(self, message: BaseMessage) -> BaseMessage:
        """Format review content with proper structure and positive tone."""
        content = message.content
        
        # Ensure proper formatting for code reviews
        if self.positive_tone and not content.startswith("#"):
            content = f"# 🌟 AI Code Review Analysis\n\n{content}"
            
        # Add structure if not present
        if "##" not in content:
            content = self._add_review_structure(content)
            
        return AIMessage(content=content)
    
    def _add_review_structure(self, content: str) -> str:
        """Add proper structure to review content in Korean."""
        if self.positive_tone:
            sections = [
                "## 🎉 잘한 점 (Positives)",
                "## 🔍 개선이 필요한 부분 (Areas for Improvement)", 
                "## 💡 제안 (Suggestions)",
                "## 🚀 계속 정진하세요 (Motivational Closure)"
            ]
        else:
            sections = [
                "## 요약 (Summary)",
                "## 코드 스타일 이슈 (Code Style)",
                "## 성능 고려사항 (Performance)", 
                "## 유지보수성 (Maintainability)",
                "## 보안 고려사항 (Security)",
                "## 개선 제안 (Suggestions)"
            ]
        
        structured_content = content
        for section in sections:
            # Check if headers exist in Korean or English (loosely)
            if section.split('(')[0].strip() not in content and section not in content:
                structured_content += f"\n\n{section}\n\n"
                
        return structured_content
    
    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "code-review-openai"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Get identifying parameters."""
        return {
            **super()._identifying_params,
            "review_style": self.review_style,
            "include_code_examples": self.include_code_examples,
            "positive_tone": self.positive_tone,
        }
