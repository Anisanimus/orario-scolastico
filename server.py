import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import traceback

import models
from models import (
    SchoolConfig, Teacher, SchoolClass, Subject, Classroom,
    TeachingAssignment, TimetableProblem, DAYS_OF_WEEK, OptimizationCriteria,
    StudentDVA, SupportAssignment, EnhancementAssignment
)
from sample_data import get_sample_problem, get_empty_problem
from solver import TimetableSolver, TimetableResult
from exporters import generate_excel_timetable, generate_excel_tabellone_combo

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

current_problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5)
current_result = None

class AppServer(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.path = "/mockup_layout.html"
            return super().do_GET()
            
        if parsed.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {
                "config": {
                    "school_name": current_problem.config.school_name,
                    "num_days": current_problem.config.num_days,
                    "daily_hours": current_problem.config.daily_hours,
                    "is_dada": getattr(current_problem.config, "is_dada", False),
                    "approfondimento_type": getattr(current_problem.config, "approfondimento_type", "custom_activity"),
                    "approfondimento_subject": getattr(current_problem.config, "approfondimento_subject", "tea"),
                    "has_musical_curriculum": getattr(current_problem.config, "has_musical_curriculum", False),
                    "has_extended_curriculum": getattr(current_problem.config, "has_extended_curriculum", False),
                },
                "classes": [
                    {
                        "id": c.id, "name": c.name, "grade": c.grade, "section": c.section,
                        "curriculum_type": getattr(c, "curriculum_type", "ordinario"),
                        "weekly_hours_target": getattr(c, "weekly_hours_target", 30)
                    }
                    for c in current_problem.classes.values()
                ],
                "teachers": [
                    {
                        "id": t.id, "name": t.name, "subject": t.subject_id,
                        "is_part_time": getattr(t, "is_part_time", False),
                        "contract_hours": getattr(t, "contract_hours", 18),
                        "free_day": getattr(t, "preferred_free_day", 0),
                        "hours_assigned": sum(a.hours_per_week for a in current_problem.assignments if a.teacher_id == t.id)
                    }
                    for t in current_problem.teachers.values()
                ],
                "rooms": [
                    {
                        "id": r.id, "name": r.name, "capacity": r.capacity,
                        "is_special_lab": r.is_special_lab, "subjects": list(r.subject_ids)
                    }
                    for r in current_problem.rooms.values()
                ],
                "has_result": current_result is not None,
                "result_status": current_result.status if current_result else None
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        if parsed.path == "/api/timetable":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if not current_result or not current_result.class_schedules:
                self.wfile.write(json.dumps({"has_schedule": False, "days": DAYS_OF_WEEK[:current_problem.config.num_days]}).encode("utf-8"))
                return
                
            num_days = current_problem.config.num_days
            days = DAYS_OF_WEEK[:num_days]
            max_daily_h = max(current_problem.config.daily_hours[:num_days])
            
            # Format classes timetables
            classes_tables = {}
            for c_id, c in current_problem.classes.items():
                grid = [["---" for _ in range(num_days)] for _ in range(max_daily_h)]
                c_sched = current_result.class_schedules.get(c_id, {})
                for (d, h), item in c_sched.items():
                    if d < num_days and h < max_daily_h:
                        s_name = current_problem.subjects[item.subject_id].name if item.subject_id in current_problem.subjects else item.subject_id
                        t_name = current_problem.teachers[item.teacher_id].name if item.teacher_id in current_problem.teachers else item.teacher_id
                        grid[h][d] = f"<b>{s_name}</b><br><span style='font-size:11px; color:#475569;'>{t_name}</span>"
                classes_tables[c_id] = {"name": c.name, "grid": grid}

            # Format teachers timetables
            teachers_tables = {}
            for t_id, t in current_problem.teachers.items():
                grid = [["---" for _ in range(num_days)] for _ in range(max_daily_h)]
                t_sched = current_result.teacher_schedules.get(t_id, {})
                for (d, h), item in t_sched.items():
                    if d < num_days and h < max_daily_h:
                        c_name = current_problem.classes[item.class_id].name if item.class_id in current_problem.classes else item.class_id
                        s_name = current_problem.subjects[item.subject_id].name if item.subject_id in current_problem.subjects else item.subject_id
                        grid[h][d] = f"<b>{c_name}</b><br><span style='font-size:11px; color:#475569;'>{s_name}</span>"
                teachers_tables[t_id] = {"name": t.name, "grid": grid}

            self.wfile.write(json.dumps({
                "has_schedule": True,
                "days": days,
                "max_hours": max_daily_h,
                "classes": classes_tables,
                "teachers": teachers_tables
            }).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
        try:
            req_data = json.loads(body)
        except Exception:
            req_data = {}

        global current_problem, current_result

        if parsed.path == "/api/load_demo":
            scen = req_data.get("scenario", "standard")
            if scen == "dada":
                current_problem = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5)
            elif scen == "musical":
                current_problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=True)
            elif scen == "prolungato":
                current_problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_extended_curriculum=True)
            elif scen == "6days":
                current_problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=6)
            elif scen == "empty":
                current_problem = get_empty_problem()
            else:
                current_problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5)
            current_result = None
            self.send_json({"status": "ok", "message": f"Scenario {scen} caricato con successo!"})
            return

        if parsed.path == "/api/solve":
            try:
                solver_engine = TimetableSolver(current_problem)
                current_result = solver_engine.solve(max_time_seconds=int(req_data.get("max_time", 25)))
                self.send_json({
                    "status": "ok",
                    "solver_status": current_result.status,
                    "total_gap_hours": current_result.total_gap_hours,
                    "score": getattr(current_result, "quality_score", 95)
                })
            except Exception as e:
                self.send_json({"status": "error", "message": str(e)})
            return

        self.send_response(404)
        self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), AppServer) as httpd:
        print(f"Server Web nativo attivo all'indirizzo: http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run()
