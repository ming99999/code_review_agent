"""FastAPI server for AI Code Review system."""

import uvicorn
import logging
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from agents.review_agent import CodeReviewAgent
from agents.analyzer_factory import AnalyzerFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Code Review API", 
    version="1.0.0",
    description="REST API for AI-powered code review system (LangGraph pipeline only)"
)

class CodeReviewRequest(BaseModel):
    code_content: str
    file_path: str
    diff_content: str = ""
    model_name: str = "gpt-4o"
    review_style: str = "comprehensive"
    include_examples: bool = True

class CodeReviewResponse(BaseModel):
    review: str
    status: str
    file_path: str

class PRReviewRequest(BaseModel):
    files: List[Dict[str, str]]  # List of {file_path: str, code_content: str, diff_content: str}
    model_name: str = "gpt-4o"
    review_style: str = "pr_markdown"

class PRReviewResponse(BaseModel):
    summary: Dict[str, Any]
    comments: List[Dict[str, Any]]
    status: str

class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"

@app.post("/review", response_model=CodeReviewResponse)
async def code_review(request: CodeReviewRequest):
    """Generate code review for the provided code content."""
    logger.info(f"Processing code review for {request.file_path}")
    logger.info(f"Code content length: {len(request.code_content) if request.code_content else 0}")
    logger.info(f"Code content preview (first 200 chars): {request.code_content[:200] if request.code_content else 'None'}")
    
    try:
        # 입력 검증
        if not request.code_content or not request.file_path:
            error_msg = f"Missing required parameters: code_content or file_path"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 코드 내용이 너무 짧은 경우 (base64 인코딩 여부 확인)
        if len(request.code_content) < 50 and "==" in request.code_content:
            error_msg = f"Invalid code content - appears to be base64 encoded: {request.file_path}"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 코드 리뷰 에이전트 초기화
        review_agent = CodeReviewAgent(
            model_name=request.model_name,
            review_style=request.review_style,
            include_examples=request.include_examples
        )
        
        # 코드 리뷰 수행
        review = review_agent.review_code(
            code_content=request.code_content,
            file_path=request.file_path,
            diff_content=request.diff_content
        )
        
        logger.info(f"Generated review length: {len(review) if review else 0}")
        logger.info(f"Review preview (first 200 chars): {review[:200] if review else 'None'}")
        
        # 리뷰 결과 검증
        if review and isinstance(review, str) and len(review.strip()) > 0:
            # 리뷰 내용이 실제 의미 있는 내용인지 확인
            if "N/A" in review and "이슈가 발견되지 않았습니다" in review:
                logger.warning(f"Review generated but appears to be empty for {request.file_path}")
            
            logger.info(f"Successfully generated review for {request.file_path}")
            return CodeReviewResponse(
                review=review,
                status="success",
                file_path=request.file_path
            )
        else:
            error_msg = f"Empty or invalid review generated for {request.file_path}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
            
    except Exception as e:
        logger.error(f"Review generation failed for {request.file_path}: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze", response_model=Dict[str, Any])
async def code_analysis(request: CodeReviewRequest):
    """Analyze code and return issues/metrics."""
    try:
        logger.info(f"Processing code analysis for {request.file_path}")
        
        # 파일 확장자에 따라 적절한 분석기 선택
        analyzer = AnalyzerFactory.create_analyzer_for_file(
            request.file_path, 
            request.diff_content
        )
        
        # 코드 분석 수행
        analysis_results = analyzer.analyze_code(
            code=request.code_content,
            file_path=request.file_path
        )
        
        logger.info(f"Successfully analyzed {request.file_path}")
        
        return {
            "status": "success",
            "file_path": request.file_path,
            "analysis": analysis_results
        }
    except Exception as e:
        logger.error(f"Code analysis failed for {request.file_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")

@app.post("/review-pr", response_model=PRReviewResponse)
async def pr_review(request: PRReviewRequest):
    """Generate PR review with summary and inline comments."""
    logger.info(f"Processing PR review for {len(request.files)} files")
    
    try:
        # 입력 검증
        if not request.files:
            error_msg = "No files provided for PR review"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 코드 리뷰 에이전트 초기화
        review_agent = CodeReviewAgent(
            model_name=request.model_name,
            review_style=request.review_style,
            include_examples=True
        )
        
        # PR 리뷰 수행
        pr_review_result = review_agent.review_pr_files(request.files)
        
        logger.info(f"Successfully generated PR review with {len(pr_review_result.get('comments', []))} comments")
        
        return PRReviewResponse(
            summary=pr_review_result.get('summary', {}),
            comments=pr_review_result.get('comments', []),
            status="success"
        )
            
    except Exception as e:
        logger.error(f"PR review generation failed: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "AI Code Review API Server",
        "version": "1.0.0",
        "endpoints": {
            "POST /review": "Generate code review",
            "POST /review-pr": "Generate PR review with summary and inline comments",
            "POST /analyze": "Analyze code for issues",
            "GET /health": "Health check",
            "GET /": "API information"
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
