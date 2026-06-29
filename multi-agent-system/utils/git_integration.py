"""
Git Integration Module
Automatic commit, branch management and version control.
"""

import asyncio
import logging
import subprocess
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GitConfig:
    """Git configuration"""
    auto_commit: bool = True
    commit_prefix: str = "[multi-agent]"
    branch_prefix: str = "agent/"
    auto_push: bool = False
    create_branch_per_project: bool = True


class GitIntegration:
    """Git integration - With smart commits"""
    
    def __init__(self, repo_path: str = ".", config: Optional[GitConfig] = None):
        self.repo_path = Path(repo_path)
        self.config = config or GitConfig()
        self._initialized = False
        self._last_commit_files: set = set()  # Files in last commit
    
    async def initialize(self):
        """Initialize Git repository"""
        if not self._is_git_repo():
            logger.info("Git repository not found, recreating...")
            await self._init_repo()
        
        self._initialized = True
        logger.info(f"Git integration started: {self.repo_path}")
    
    def _is_git_repo(self) -> bool:
        """Check if Git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    async def _init_repo(self):
        """Initialize new Git repository"""
        try:
            subprocess.run(
                ["git", "init"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            gitignore_content = """
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/
data/
*.db
*.sqlite
output/
node_modules/
"""
            gitignore_path = self.repo_path / ".gitignore"
            gitignore_path.write_text(gitignore_content.strip())
            
            await self._run_git(["add", "."])
            await self._run_git(["commit", "-m", f"{self.config.commit_prefix} Initial setup"])
            
            logger.info("Git repository created")
            
        except Exception as e:
            logger.error(f"Git repo creation error: {e}")
    
    async def _run_git(self, args: List[str], check: bool = True) -> Dict[str, Any]:
        """Execute Git command"""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if check and result.returncode != 0:
                logger.error(f"Git error: {result.stderr}")
                return {"success": False, "error": result.stderr}
            
            return {
                "success": True,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Git command timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "Git not found"}
    
    async def create_branch(self, branch_name: str) -> bool:
        """Create new branch"""
        full_name = f"{self.config.branch_prefix}{branch_name}"
        
        await self._auto_commit_if_needed(f"Previous changes - {full_name}")
        
        result = await self._run_git(["checkout", "-b", full_name])
        
        if result["success"]:
            logger.info(f"Branch created: {full_name}")
            return True
        else:
            logger.error(f"Branch creation error: {result.get('error')}")
            return False
    
    async def commit_changes(self, message: str, files: Optional[List[str]] = None, 
                            validate: bool = True) -> bool:
        """Commit changes - With validation"""
        # Check changes
        status = await self._run_git(["status", "--porcelain"])
        changed_files = status.get("stdout", "").strip().split("\n") if status.get("stdout") else []
        
        if not changed_files or changed_files == ['']:
            logger.debug("No changes to commit")
            return True
        
        # Filter meaningful changes
        meaningful_files = self._filter_meaningful_changes(changed_files)
        
        if not meaningful_files:
            logger.debug("No meaningful changes - skipping")
            return True
        
        # Add files
        if files:
            for file in files:
                await self._run_git(["add", file])
        else:
            for file in meaningful_files:
                await self._run_git(["add", file])
        
        # Commit
        full_message = f"{self.config.commit_prefix} {message}"
        result = await self._run_git(["commit", "-m", full_message])
        
        if result["success"]:
            self._last_commit_files = set(meaningful_files)
            logger.info(f"Commit successful: {message} ({len(meaningful_files)} files)")
            return True
        else:
            logger.error(f"Commit error: {result.get('error')}")
            return False
    
    def _filter_meaningful_changes(self, files: List[str]) -> List[str]:
        """Filter meaningful changes"""
        meaningful = []
        
        # Exclude meaningless files
        skip_patterns = [
            '.pyc', '__pycache__', '.pyo', 
            '.db', '.sqlite', '.log',
            '.DS_Store', 'Thumbs.db',
            'desktop.ini',
        ]
        
        for file in files:
            # Clean file name
            clean_file = file.strip()
            if clean_file.startswith('M ') or clean_file.startswith('A '):
                clean_file = clean_file[2:]
            elif clean_file.startswith('?? ') or clean_file.startswith(' D '):
                continue
            
            # Files to skip
            if any(pattern in clean_file for pattern in skip_patterns):
                continue
            
            # Empty file check
            file_path = self.repo_path / clean_file
            if file_path.exists() and file_path.stat().st_size == 0:
                continue
            
            meaningful.append(clean_file)
        
        return meaningful
    
    async def _auto_commit_if_needed(self, default_message: str = "Auto commit"):
        """Auto-commit if needed"""
        if not self.config.auto_commit:
            return
        
        status = await self._run_git(["status", "--porcelain"])
        if status.get("stdout"):
            await self.commit_changes(default_message)
    
    async def get_status(self) -> Dict[str, Any]:
        """Get Git status"""
        status = await self._run_git(["status", "--porcelain"])
        log = await self._run_git(["log", "--oneline", "-5"])
        branch = await self._run_git(["branch", "--show-current"])
        
        return {
            "branch": branch.get("stdout", "unknown"),
            "has_changes": bool(status.get("stdout")),
            "changed_files": status.get("stdout", "").split("\n") if status.get("stdout") else [],
            "recent_commits": log.get("stdout", "").split("\n") if log.get("stdout") else [],
        }
    
    async def push(self, remote: str = "origin", branch: Optional[str] = None) -> bool:
        """Push changes"""
        if not self.config.auto_push:
            logger.info("Auto-push disabled")
            return False
        
        args = ["push", remote]
        if branch:
            args.append(branch)
        
        result = await self._run_git(args)
        
        if result["success"]:
            logger.info("Push successful")
            return True
        else:
            logger.error(f"Push error: {result.get('error')}")
            return False
    
    async def create_version_tag(self, tag_name: str, message: str = "") -> bool:
        """Create version tag"""
        result = await self._run_git(["tag", "-a", tag_name, "-m", message or tag_name])
        
        if result["success"]:
            logger.info(f"Tag created: {tag_name}")
            return True
        else:
            logger.error(f"Tag creation error: {result.get('error')}")
            return False


class ProjectGitManager:
    """Project-based Git management"""
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self._integrations: Dict[str, GitIntegration] = {}
    
    async def create_project_repo(self, project_name: str) -> GitIntegration:
        """Create repository for project"""
        project_path = self.base_path / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        config = GitConfig(
            auto_commit=True,
            commit_prefix=f"[{project_name}]",
            branch_prefix=f"feature/",
            create_branch_per_project=True
        )
        
        git = GitIntegration(str(project_path), config)
        await git.initialize()
        
        self._integrations[project_name] = git
        return git
    
    def get_project_git(self, project_name: str) -> Optional[GitIntegration]:
        """Get Git integration for project"""
        return self._integrations.get(project_name)


def init_project_repo(project_root: Path) -> None:
    """Initialize a git repository in the given directory."""
    project_root.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["git", "init"], cwd=project_root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "multi-agent-system"], cwd=project_root, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "agent@example.com"], cwd=project_root, capture_output=True, check=True)
        logger.info(f"Git repository initialized at {project_root}")
    except FileNotFoundError:
        logger.warning("Git not found: commits will not be created")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else str(exc)
        logger.warning(f"Git init error: {stderr}")
