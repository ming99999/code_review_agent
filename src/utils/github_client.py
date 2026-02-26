"""GitHub API client for PR operations."""

import os
import base64
import requests
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """Represents a file change in a PR."""
    filename: str
    status: str  # added, modified, removed
    additions: int
    deletions: int
    changes: int
    patch: str
    raw_url: str
    contents_url: str


@dataclass
class PRDetails:
    """Pull Request details."""
    number: int
    title: str
    body: str
    state: str
    head_sha: str
    base_sha: str
    author: str
    created_at: str
    updated_at: str
    files_changed: List[FileChange]


class GitHubClient:
    """GitHub API client for code review operations."""
    
    def __init__(self, token: str = None):
        """Initialize GitHub client.
        
        Args:
            token: GitHub personal access token. If None, uses GITHUB_TOKEN env var.
        """
        self.token = token or os.getenv('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable.")
        
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Code-Reviewer/1.0"
        }
    
    def get_pr_details(self, repo: str, pr_number: int) -> PRDetails:
        """Get pull request details.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            
        Returns:
            PRDetails object with PR information
        """
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            pr_data = response.json()
            
            # Get changed files
            files_url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/files"
            files_response = requests.get(files_url, headers=self.headers)
            files_response.raise_for_status()
            
            files_data = files_response.json()
            file_changes = []
            
            for file_data in files_data:
                file_change = FileChange(
                    filename=file_data['filename'],
                    status=file_data['status'],
                    additions=file_data['additions'],
                    deletions=file_data['deletions'],
                    changes=file_data['changes'],
                    patch=file_data.get('patch', ''),
                    raw_url=file_data['raw_url'],
                    contents_url=file_data['contents_url']
                )
                file_changes.append(file_change)
            
            return PRDetails(
                number=pr_data['number'],
                title=pr_data['title'],
                body=pr_data['body'] or "",
                state=pr_data['state'],
                head_sha=pr_data['head']['sha'],
                base_sha=pr_data['base']['sha'],
                author=pr_data['user']['login'],
                created_at=pr_data['created_at'],
                updated_at=pr_data['updated_at'],
                files_changed=file_changes
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get PR details: {e}")
            raise
    
    def get_file_content_at_sha(self, repo: str, file_path: str, sha: str) -> str:
        """Get file content at specific commit SHA.
        
        Args:
            repo: Repository in format "owner/repo"
            file_path: Path to the file
            sha: Commit SHA
            
        Returns:
            File content as string
        """
        url = f"{self.base_url}/repos/{repo}/contents/{file_path}?ref={sha}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            file_data = response.json()
            
            # Decode base64 content
            if file_data.get('encoding') == 'base64':
                content = base64.b64decode(file_data['content']).decode('utf-8')
                return content
            else:
                logger.warning(f"Unexpected encoding: {file_data.get('encoding')}")
                return ""
                
        except requests.exceptions.RequestException as e:
            if response.status_code == 404:
                logger.warning(f"File {file_path} not found at SHA {sha}")
                return ""  # File might be new in PR
            logger.error(f"Failed to get file content: {e}")
            raise
    
    def get_file_content_from_pr(self, repo: str, pr_number: int, file_path: str) -> Tuple[str, str]:
        """Get file content from both base and head of PR.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            file_path: Path to the file
            
        Returns:
            Tuple of (base_content, head_content)
        """
        pr_details = self.get_pr_details(repo, pr_number)
        
        base_content = self.get_file_content_at_sha(
            repo, file_path, pr_details.base_sha
        )
        head_content = self.get_file_content_at_sha(
            repo, file_path, pr_details.head_sha
        )
        
        return base_content, head_content
    
    def post_review_comment(self, repo: str, pr_number: int, body: str, commit_id: str = None) -> Dict[str, Any]:
        """Post a review comment on a pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            body: Comment body (Markdown format)
            commit_id: Optional commit SHA to attach comment to
            
        Returns:
            API response data
        """
        url = f"{self.base_url}/repos/{repo}/issues/{pr_number}/comments"
        
        data = {
            "body": body
        }
        
        if commit_id:
            data["commit_id"] = commit_id
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            
            logger.info(f"Posted review comment to PR #{pr_number}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post comment: {e}")
            raise
    
    def post_inline_comment(
        self, 
        repo: str, 
        pr_number: int, 
        body: str, 
        commit_id: str, 
        path: str, 
        line: int,
        side: str = "RIGHT"
    ) -> Dict[str, Any]:
        """Post an inline comment on a specific line of a pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            body: Comment body
            commit_id: Commit SHA to attach comment to
            path: File path
            line: Line number
            side: "LEFT" or "RIGHT" (changeset side)
            
        Returns:
            API response data
        """
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}/comments"
        
        data = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": side
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=data)
            response.raise_for_status()
            
            logger.info(f"Posted inline comment on {path}:{line}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post inline comment: {e}")
            raise
    
    def create_or_update_comment(
        self, 
        repo: str, 
        pr_number: int, 
        body: str, 
        comment_identifier: str = "🤖 AI Code Review"
    ) -> Dict[str, Any]:
        """Create or update a review comment to avoid duplicates.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            body: Comment body
            comment_identifier: Unique identifier to find existing comments
            
        Returns:
            API response data
        """
        # Get existing comments
        url = f"{self.base_url}/repos/{repo}/issues/{pr_number}/comments"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            comments = response.json()
            
            # Find existing AI review comment
            existing_comment = None
            for comment in comments:
                if comment_identifier in comment.get('body', ''):
                    existing_comment = comment
                    break
            
            # Prepare comment body with identifier
            full_body = f"{comment_identifier}\n\n{body}"
            
            if existing_comment:
                # Update existing comment
                update_url = f"{self.base_url}/repos/{repo}/issues/comments/{existing_comment['id']}"
                response = requests.patch(update_url, headers=self.headers, json={"body": full_body})
                response.raise_for_status()
                logger.info(f"Updated existing review comment")
            else:
                # Create new comment
                response = requests.post(url, headers=self.headers, json={"body": full_body})
                response.raise_for_status()
                logger.info(f"Created new review comment")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to create/update comment: {e}")
            raise
    
    def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Get the diff of a pull request.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            
        Returns:
            Diff content as string
        """
        url = f"{self.base_url}/repos/{repo}/pulls/{pr_number}"
        headers = self.headers.copy()
        headers["Accept"] = "application/vnd.github.v3.diff"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get PR diff: {e}")
            raise