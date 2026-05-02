"""
SpecForge v7.2.1 – Iterative coding with feedback-driven fixes.
- Preserves previous code and passes it to coders on retry.
- QA feedback is injected into coders together with the old code.
- Increased timeout to 10 minutes.
- Robust JSON parsing, context truncation, and defensive error handling.
"""
import json
import os
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from crewai.flow import Flow, start, listen, router

from .pipeline_state import PipelineState, UserStory
from ..crews.loader import get_crew
from ..tools.sanitizer import sanitize_generated_code

logger = logging.getLogger("specforge.flow")

CREW_TIMEOUT = 3600  # 60 minutes for code generation


def _run_crew_with_timeout(crew, inputs: dict) -> str:
    """Run crew.kickoff with timeout protection and clear error logging."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(crew.kickoff, inputs=inputs)
        try:
            result = future.result(timeout=CREW_TIMEOUT)
            return result.raw
        except FuturesTimeoutError:
            logger.error(f"⏰ Crew timed out after {CREW_TIMEOUT}s (inputs: {list(inputs.keys())})")
            raise TimeoutError(f"Crew execution timed out after {CREW_TIMEOUT} seconds")


class SpecForgeFlow(Flow[PipelineState]):

    # =========================================================================
    # Phase 1: Research
    # =========================================================================
    @start()
    def research(self, **kwargs) -> str:
        project_idea = kwargs.get("project_idea", "")
        logger.info(f"🔍 Phase 1: Research... (Project: {project_idea[:60]}...)")
        self.state.project_idea = project_idea

        try:
            crew = get_crew("researcher")
            self.state.research_report = _run_crew_with_timeout(crew, {"project_idea": project_idea})
        except Exception as e:
            logger.error(f"❌ Research crew failed: {e}")
            self.state.errors.append(f"research_failed: {e}")
            self.state.research_report = ""
        return self.state.research_report

    # =========================================================================
    # Phase 2: Business Analysis (inline retry with robust JSON)
    # =========================================================================
    @listen(research)
    def business_analysis(self, research_report: str) -> List[UserStory]:
        logger.info("📋 Phase 2: Business Analysis...")
        self.state.ba_retries = 0

        for attempt in range(self.state.max_retries + 1):
            try:
                crew = get_crew("ba")
                raw = _run_crew_with_timeout(crew, {
                    "research": research_report,
                    "project_idea": self.state.project_idea
                })
            except Exception as e:
                logger.warning(f"⚠️ BA crew failed (attempt {attempt+1}): {e}")
                if attempt >= self.state.max_retries:
                    self.state.errors.append(f"ba_crew_failed: {e}")
                    self.state.user_stories = []
                    return []
                continue

            try:
                cleaned = re.sub(r'```json\s*|\s*```', '', raw)
                first = cleaned.find('[')
                last = cleaned.rfind(']')
                if first != -1 and last != -1:
                    json_candidate = cleaned[first:last+1]
                    stories = json.loads(json_candidate)
                else:
                    match = re.search(r'\[.*\]', cleaned, re.DOTALL)
                    if match:
                        stories = json.loads(match.group(0))
                    else:
                        raise ValueError("No JSON array found")

                if not isinstance(stories, list):
                    stories = [stories]

                normalized = []
                for story in stories:
                    if isinstance(story, dict):
                        if "priorities" in story and "priority" not in story:
                            story["priority"] = story.pop("priorities")
                        normalized.append(story)

                user_stories = []
                for story in normalized:
                    try:
                        user_stories.append(UserStory(**story))
                    except Exception as e:
                        logger.warning(f"⚠️ Invalid story: {e}")

                if user_stories:
                    self.state.user_stories = user_stories
                    logger.info(f"✅ BA parsed {len(user_stories)} stories after {attempt+1} attempt(s)")
                    return user_stories

            except Exception as e:
                logger.warning(f"⚠️ BA JSON parse failed (attempt {attempt+1}): {e}")
                if attempt < self.state.max_retries:
                    logger.info(f"🔄 Retrying BA (attempt {attempt+2}/{self.state.max_retries+1})...")
                continue

        logger.error("❌ Max BA retries exceeded, aborting")
        self.state.errors.append("ba_failed_all_retries")
        self.state.user_stories = []
        return []

    @router(business_analysis)
    def ba_router(self, stories: List[UserStory]) -> str:
        if not stories:
            return "abort"
        return "proceed_to_pm"

    @listen("abort")
    def abort_pipeline(self) -> str:
        logger.error("🛑 Pipeline aborted due to BA failures")
        self.state.is_ready = False
        return "pipeline_aborted"

    # =========================================================================
    # Phase 3: Project Management
    # =========================================================================
    @listen("proceed_to_pm")
    def project_management(self) -> dict:
        logger.info("📦 Phase 3: Project Management...")
        if not self.state.user_stories:
            return {"status": "fail", "errors": ["No user stories"]}

        try:
            crew = get_crew("pm")
            raw = _run_crew_with_timeout(crew, {
                "project_idea": self.state.project_idea,
                "user_stories": json.dumps([s.model_dump() for s in self.state.user_stories])
            })
        except Exception as e:
            logger.error(f"❌ PM crew failed: {e}")
            self.state.errors.append(f"pm_crew_failed: {e}")
            return {"status": "fail", "errors": [str(e)]}

        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            self.state.pm_report = json.loads(match.group(0) if match else raw)
            logger.info(f"✅ PM: Repo={self.state.pm_report.get('repo_url')}, Issues={len(self.state.pm_report.get('issues_created', []))}")
        except Exception as e:
            logger.error(f"❌ PM JSON parse failed: {e}")
            self.state.pm_report = {"status": "fail", "errors": [str(e)]}
        return self.state.pm_report

    @router(project_management)
    def pm_router(self, report: dict) -> str:
        if report.get("status") == "success" and report.get("repo_url"):
            self.state.pm_success = True
        else:
            self.state.pm_success = False
            logger.warning("⚠️ PM failed but continuing with local-only flow...")
        return "proceed_to_arch"

    # =========================================================================
    # Phase 4: Architecture
    # =========================================================================
    @listen("proceed_to_arch")
    def architecture(self) -> str:
        logger.info("🏗️ Phase 4: Architecture...")
        if not self.state.user_stories:
            self.state.sdd_markdown = ""
            return ""

        try:
            crew = get_crew("architect")
            self.state.sdd_markdown = _run_crew_with_timeout(crew, {
                "user_stories": json.dumps([s.model_dump() for s in self.state.user_stories])
            })
        except Exception as e:
            logger.error(f"❌ Architect failed: {e}")
            self.state.errors.append(f"architect_failed: {e}")
            self.state.sdd_markdown = ""
        return self.state.sdd_markdown

    # =========================================================================
    # Phase 5+6+7: Code + QA with feedback‑driven iterative fixes
    # =========================================================================
    @router(architecture)
    def code_and_qa(self, sdd: str) -> str:
        logger.info("🧑‍💻 Code + QA with iterative fixes (previous code preserved)...")
        max_attempts = self.state.max_retries + 1
        qa_feedback = ""
        prev_backend_code = ""
        prev_frontend_code = ""
        self.state.is_ready = False

        for attempt in range(max_attempts):
            self.state.code_retries = attempt  # Track current attempt for summary
            logger.info(f"🔄 Attempt {attempt+1}/{max_attempts}")

            backend_ok = self._generate_backend(sdd, qa_feedback, prev_backend_code)
            frontend_ok = self._generate_frontend(sdd, qa_feedback, prev_frontend_code)

            if not backend_ok and not frontend_ok:
                logger.warning("⚠️ No code generated. Skipping QA.")
                self.state.qa_report = {"status": "fail", "error": "No code generated"}
                break

            qa_feedback = self._run_qa()
            if qa_feedback and len(qa_feedback) > 200:
                logger.debug(f"📝 QA Feedback for next attempt: {qa_feedback[:200]}...")

            if self.state.qa_report.get("status") == "pass":
                self.state.is_ready = True
                logger.info("✅ QA passed.")
                break

            # Prepare for next iteration: store current code to fix
            prev_backend_code = self.state.backend_code
            prev_frontend_code = self.state.frontend_code
            logger.info("⚠️ QA failed. Storing previous code for next attempt.")

        self._generate_summary()
        return "export"

    def _generate_backend(self, sdd: str, feedback: str, previous_code: str) -> bool:
        try:
            # Truncate previous_code to avoid context window overflow
            MAX_CODE_CHARS = 8000
            if previous_code and len(previous_code) > MAX_CODE_CHARS:
                previous_code = previous_code[:MAX_CODE_CHARS] + "\n# ... (truncated for context)"

            crew = get_crew("backend_coder")
            raw = _run_crew_with_timeout(crew, {
                "sdd": sdd,
                "project_idea": self.state.project_idea,
                "qa_feedback": feedback,
                "previous_code": previous_code
            })
            self.state.backend_code = sanitize_generated_code(raw, "python")
            logger.info("✅ Backend sanitized")
            return True
        except Exception as e:
            logger.error(f"❌ Backend failed: {e}")
            self.state.errors.append(f"backend_failed: {e}")
            self.state.backend_code = ""
            return False

    def _generate_frontend(self, sdd: str, feedback: str, previous_code: str) -> bool:
        try:
            # Truncate previous_code to avoid context window overflow
            MAX_CODE_CHARS = 8000
            if previous_code and len(previous_code) > MAX_CODE_CHARS:
                previous_code = previous_code[:MAX_CODE_CHARS] + "\n# ... (truncated for context)"

            crew = get_crew("frontend_coder")
            raw = _run_crew_with_timeout(crew, {
                "sdd": sdd,
                "project_idea": self.state.project_idea,
                "qa_feedback": feedback,
                "previous_code": previous_code,
                "API_BASE": os.getenv("OPENAI_API_BASE", "http://localhost:11434"),
                "token": "",  # Empty string is fine for optional template vars
            })
            self.state.frontend_code = sanitize_generated_code(raw, "typescript")
            logger.info("✅ Frontend sanitized")
            return True
        except Exception as e:
            logger.error(f"❌ Frontend failed: {e}")
            self.state.errors.append(f"frontend_failed: {e}")
            self.state.frontend_code = ""
            return False

    def _run_qa(self) -> str:
        logger.info("🧪 Running QA...")
        try:
            crew = get_crew("qa")
            raw = _run_crew_with_timeout(crew, {
                "backend": self.state.backend_code,
                "frontend": self.state.frontend_code,
                "project_idea": self.state.project_idea,
                "sdd": self.state.sdd_markdown
            })

            # 🔧 Robust JSON extraction: strip markdown fences, backticks, trailing commas
            cleaned = re.sub(r'```json\s*|\s*```', '', raw).strip()
            cleaned = cleaned.replace('`', '"')  # Replace backticks with quotes
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)  # Remove trailing commas before } or ]

            # Find JSON object with balanced braces (handles nested objects)
            brace_count = 0
            start_idx = -1
            for i, ch in enumerate(cleaned):
                if ch == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        json_str = cleaned[start_idx:i+1]
                        break
            else:
                # Fallback: greedy match if brace counting fails
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                json_str = match.group(0) if match else cleaned

            self.state.qa_report = json.loads(json_str)

            # Build actionable feedback for next retry
            failed = self.state.qa_report.get("failed", [])
            blocking = self.state.qa_report.get("blocking_issues", [])
            notes = self.state.qa_report.get("coverage_notes", "")[:150]  # Truncate notes

            feedback_parts = []
            if failed:
                feedback_parts.append(f"❌ Failed tests: {', '.join(failed)}")
            if blocking:
                feedback_parts.append(f"🚫 Blocking: {', '.join(blocking)}")
            if notes:
                feedback_parts.append(f"📝 Notes: {notes}")

            return "\n".join(feedback_parts) if feedback_parts else "QA completed."

        except Exception as e:
            logger.error(f"❌ QA failed/parse error: {e}")
            self.state.errors.append(f"qa_failed: {e}")
            # Ensure minimal structure for summary generation
            self.state.qa_report = {
                "status": "fail",
                "error": str(e),
                "failed": [],
                "blocking_issues": [f"QA output unparsable: {e}"]
            }
            return f"QA parse error: {e}"

    def _generate_summary(self):
        """Creates human-readable summary.md with QA findings."""
        status_icon = "✅ READY" if self.state.is_ready else "⚠️ COMPLETED WITH ISSUES"

        # QA findings section
        qa_section = []
        if self.state.qa_report:
            qa_status = self.state.qa_report.get("status", "unknown")
            qa_section.append(f"**QA Status**: {qa_status.upper()}")

            if self.state.qa_report.get("tests"):
                qa_section.append(f"- Tests: {self.state.qa_report['tests']}")
            if self.state.qa_report.get("passed"):
                qa_section.append(f"- ✅ Passed: {len(self.state.qa_report['passed'])} tests")
            if self.state.qa_report.get("failed"):
                qa_section.append(f"- ❌ Failed: {len(self.state.qa_report['failed'])} tests")
            if self.state.qa_report.get("blocking_issues"):
                qa_section.append("\n### 🚫 Blocking Issues (Manual Review Required)")
                for issue in self.state.qa_report["blocking_issues"]:
                    qa_section.append(f"- {issue}")

        lines = [
            f"# Pipeline Run Summary",
            f"**Project**: {self.state.project_idea}",
            f"**Overall Status**: {status_icon}",
            f"**Retries Used**: BA={self.state.ba_retries}, Code/QA={self.state.code_retries}",
            "",
            "## Artifacts Generated",
            f"- Backend: {'✅ Yes' if self.state.backend_code else '❌ Failed'}",
            f"- Frontend: {'✅ Yes' if self.state.frontend_code else '❌ Failed'}",
            f"- QA Report: {'✅ Yes' if self.state.qa_report else '❌ Skipped'}",
            "",
            "## QA Findings",
            *(qa_section if qa_section else ["- No QA report available"]),
            "",
            "## Notes & Errors",
        ]

        if self.state.errors:
            for err in self.state.errors[-5:]:  # Last 5 errors only
                lines.append(f"- ⚠️ {err}")
        else:
            lines.append("- ✅ No critical errors recorded.")

        self.state.pipeline_summary = "\n".join(lines)
        

    # =========================================================================
    # Export & Helpers
    # =========================================================================
    @listen("export")
    def export_artifacts(self) -> str:
        logger.info("📦 Exporting final artifacts...")
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            output_dir = Path("output/runs") / timestamp
            output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Export directory: {output_dir}")

            latest_path = Path("output/runs/latest")
            self._update_latest_pointer(latest_path, timestamp)

            if self.state.backend_code:
                (output_dir / "backend.py").write_text(self.state.backend_code, encoding="utf-8")
                logger.info("✅ Wrote backend.py")
            if self.state.frontend_code:
                (output_dir / "frontend.tsx").write_text(self.state.frontend_code, encoding="utf-8")
                logger.info("✅ Wrote frontend.tsx")
            if self.state.qa_report:
                (output_dir / "qa_report.json").write_text(json.dumps(self.state.qa_report, indent=2))
                logger.info("✅ Wrote qa_report.json")
            if hasattr(self.state, "pipeline_summary"):
                (output_dir / "summary.md").write_text(self.state.pipeline_summary, encoding="utf-8")
                logger.info("✅ Wrote summary.md")

            metadata = {
                "project_idea": self.state.project_idea,
                "is_ready": self.state.is_ready,
                "pm_success": self.state.pm_success,
                "errors": self.state.errors,
                "retries": {"ba": self.state.ba_retries, "code": self.state.code_retries},
                "timestamp": timestamp
            }
            (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
            logger.info("✅ Wrote metadata.json")

            if self.state.pm_success and self.state.pm_report:
                pm_info = {
                    "repo_url": self.state.pm_report.get("repo_url"),
                    "issues_created": self.state.pm_report.get("issues_created", [])
                }
                (output_dir / "github_info.json").write_text(json.dumps(pm_info, indent=2))
                logger.info("✅ Wrote github_info.json")

        except Exception as e:
            logger.error(f"❌ Export failed: {e}")
            self.state.errors.append(f"export_failed: {e}")

        return "pipeline_complete"

    def _update_latest_pointer(self, latest_path: Path, target_timestamp: str) -> None:
        target_dir_name = target_timestamp
        try:
            if latest_path.exists() or latest_path.is_symlink():
                latest_path.unlink()
            latest_path.symlink_to(target_dir_name, target_is_directory=True)
            logger.info("✅ Created 'latest' symlink")
        except (OSError, NotImplementedError) as e:
            logger.warning(f"⚠️ Could not create symlink, using fallback file: {e}")
            fallback_file = latest_path.parent / "latest.txt"
            fallback_file.write_text(target_dir_name, encoding="utf-8")
            logger.info(f"✅ Wrote fallback 'latest.txt' -> {target_dir_name}")

    @listen(abort_pipeline)
    def handle_abort(self) -> str:
        logger.error(f"🛑 Pipeline aborted. Final errors: {self.state.errors}")
        return "aborted"