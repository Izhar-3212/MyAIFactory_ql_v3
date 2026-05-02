"""
SpecForge v6.1.0 – Production‑grade with internal retry loop for code generation + QA.
Uses method references for final export and abort handlers (no fragile string signals).
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from crewai.flow import Flow, start, listen, router

from .pipeline_state import PipelineState, UserStory
from ..crews.loader import get_crew
from ..tools.sanitizer import sanitize_generated_code

logger = logging.getLogger("specforge.flow")


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
            self.state.research_report = crew.kickoff(inputs={"project_idea": project_idea}).raw
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
                raw = crew.kickoff(inputs={
                    "research": research_report,
                    "project_idea": self.state.project_idea
                }).raw
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
        """Emit abort signal (will be caught by handle_abort via method reference)."""
        logger.error("🛑 Pipeline aborted due to BA failures")
        self.state.is_ready = False
        return "pipeline_aborted"  # value ignored, but method reference triggers handle_abort

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
            raw = crew.kickoff(inputs={
                "project_idea": self.state.project_idea,
                "user_stories": json.dumps([s.model_dump() for s in self.state.user_stories])
            }).raw
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
            self.state.sdd_markdown = crew.kickoff(inputs={
                "user_stories": json.dumps([s.model_dump() for s in self.state.user_stories])
            }).raw
        except Exception as e:
            logger.error(f"❌ Architect failed: {e}")
            self.state.errors.append(f"architect_failed: {e}")
            self.state.sdd_markdown = ""
        return self.state.sdd_markdown

    # =========================================================================
    # Phase 5+6+7: Code + QA with internal retry loop (GUARANTEED RETRIES)
    # =========================================================================
    @listen(architecture)
    def code_and_qa(self, sdd: str) -> str:
        """
        Generates backend/frontend code and runs QA in a loop until success or max retries.
        Returns (unused) – export is triggered by method reference.
        """
        logger.info("🧑‍💻 Phase 5+6+7: Code generation + QA with internal retries...")

        if not sdd:
            logger.error("❌ No SDD available")
            self.state.qa_report = {"status": "fail", "error": "No SDD"}
            return "export"

        max_attempts = self.state.max_retries + 1
        for attempt in range(max_attempts):
            logger.info(f"🔄 Code+QA attempt {attempt+1}/{max_attempts}")

            # ---- Code generation ----
            backend_ok = False
            frontend_ok = False
            try:
                crew = get_crew("backend_coder")
                raw_backend = crew.kickoff(inputs={"sdd": sdd, "project_idea": self.state.project_idea}).raw
                self.state.backend_code = sanitize_generated_code(raw_backend, "python")
                backend_ok = True
                logger.info("✅ Backend generated")
            except Exception as e:
                logger.error(f"❌ Backend failed: {e}")
                self.state.errors.append(f"backend_failed_attempt_{attempt+1}: {e}")
                self.state.backend_code = ""

            try:
                crew = get_crew("frontend_coder")
                raw_frontend = crew.kickoff(inputs={"sdd": sdd, "project_idea": self.state.project_idea}).raw
                self.state.frontend_code = sanitize_generated_code(raw_frontend, "typescript")
                frontend_ok = True
                logger.info("✅ Frontend generated")
            except Exception as e:
                logger.error(f"❌ Frontend failed: {e}")
                self.state.errors.append(f"frontend_failed_attempt_{attempt+1}: {e}")
                self.state.frontend_code = ""

            if not backend_ok and not frontend_ok:
                logger.warning("⚠️ No code generated, skipping QA")
                self.state.qa_report = {"status": "fail", "error": "No code generated"}
                self.state.is_ready = False
                if attempt + 1 < max_attempts:
                    continue
                else:
                    break

            # ---- QA ----
            logger.info("🧪 Running QA...")
            try:
                crew = get_crew("qa")
                raw = crew.kickoff(inputs={
                    "backend": self.state.backend_code,
                    "frontend": self.state.frontend_code,
                    "project_idea": self.state.project_idea
                }).raw
            except Exception as e:
                logger.error(f"❌ QA crew failed: {e}")
                self.state.errors.append(f"qa_crew_failed_attempt_{attempt+1}: {e}")
                self.state.qa_report = {"status": "fail", "error": str(e)}
                self.state.is_ready = False
                if attempt + 1 < max_attempts:
                    continue
                else:
                    break

            # Robust JSON extraction
            try:
                cleaned = re.sub(r'```json\s*|\s*```', '', raw)
                match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
                if not match:
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                json_str = match.group(0) if match else cleaned
                self.state.qa_report = json.loads(json_str)
            except Exception as e:
                logger.error(f"❌ QA JSON parse failed: {e}")
                logger.debug(f"Raw QA output: {raw[:500]}")
                self.state.qa_report = {"status": "fail", "error": f"JSON parse error: {e}"}

            passed = self.state.qa_report.get("status") == "pass"
            self.state.is_ready = passed

            if passed:
                logger.info(f"✅ QA passed on attempt {attempt+1}")
                self.state.code_retries = attempt
                break
            else:
                logger.warning(f"⚠️ QA failed on attempt {attempt+1}")
                if attempt + 1 < max_attempts:
                    logger.info(f"🔄 Retrying code+QA (attempt {attempt+2}/{max_attempts})...")

        logger.info(f"📦 Code+QA finished. Final status: is_ready={self.state.is_ready}")
        # Return value is ignored – export is triggered by method reference below
        return "export"

    # =========================================================================
    # Final Export (listens to method completion, not a string)
    # =========================================================================
    @listen(code_and_qa)
    def export_artifacts(self) -> str:
        """Write all artifacts to timestamped directory."""
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

    # =========================================================================
    # Abort handler – listens to method reference, not string signal
    # =========================================================================
    @listen(abort_pipeline)
    def handle_abort(self) -> str:
        """Final abort handler."""
        logger.error(f"🛑 Pipeline aborted. Final errors: {self.state.errors}")
        return "aborted"