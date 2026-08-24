"""Modulo per l'editing manuale e la riparazione intelligente (Smart Repair / LNS) dell'orario scolastico."""
import copy
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from models import TimetableProblem
from solver import TimetableResult, TimetableSolver, LessonSlotInfo

SlotInfo = LessonSlotInfo
from schedule_validator import validate_timetable, ValidationReport
from ortools.sat.python import cp_model

@dataclass
class SwapProposal:
    proposal_id: str
    description: str
    changes_count: int
    resulting_result: TimetableResult
    report: ValidationReport
    changes_details: List[str] = field(default_factory=list)

def apply_direct_swap(
    problem: TimetableProblem,
    result: TimetableResult,
    class_id: str,
    day_a: int,
    hour_a: int,
    day_b: int,
    hour_b: int
) -> Tuple[TimetableResult, ValidationReport]:
    """Esegue uno scambio diretto atomico tra due slot di una classe e restituisce il nuovo risultato e il report."""
    new_res = copy.deepcopy(result)
    c_grid = new_res.grid_by_class.get(class_id)
    if not c_grid:
        return result, validate_timetable(problem, result)
        
    slot_a = copy.deepcopy(c_grid[day_a][hour_a]) if day_a < len(c_grid) and hour_a < len(c_grid[day_a]) else None
    slot_b = copy.deepcopy(c_grid[day_b][hour_b]) if day_b < len(c_grid) and hour_b < len(c_grid[day_b]) else None
    
    # Esegui lo scambio nella griglia della classe
    c_grid[day_a][hour_a] = slot_b
    c_grid[day_b][hour_b] = slot_a
    
    # Ricostruisci le viste per docente, aula e statistiche
    _rebuild_result_views(problem, new_res)
    
    report = validate_timetable(problem, new_res)
    return new_res, report

def _rebuild_result_views(problem: TimetableProblem, res: TimetableResult):
    """Rigenera in modo consistente grid_by_teacher, grid_by_room, gaps e statistiche da grid_by_class."""
    days = getattr(problem.config, "active_days", None) or getattr(problem.config, "days", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])[:problem.config.num_days]
    daily_h = getattr(problem.config, "daily_hours", [6]*5)[:problem.config.num_days]
    
    # Inizializza griglie docenti e aule
    res.grid_by_teacher = {
        t_id: [[None for _ in range(daily_h[d])] for d in range(len(days))]
        for t_id in problem.teachers.keys()
    }
    res.grid_by_room = {
        r_id: [[None for _ in range(daily_h[d])] for d in range(len(days))]
        for r_id in problem.rooms.keys()
    }
    
    # Popola da grid_by_class
    for c_id, c_grid in res.grid_by_class.items():
        for d in range(len(days)):
            for h in range(daily_h[d]):
                slot = c_grid[d][h] if d < len(c_grid) and h < len(c_grid[d]) else None
                if slot is not None:
                    t_id = slot.teacher_id
                    if t_id and t_id in res.grid_by_teacher:
                        res.grid_by_teacher[t_id][d][h] = slot
                        
                    r_id = slot.room_id
                    if r_id and r_id in res.grid_by_room:
                        res.grid_by_room[r_id][d][h] = slot

    # Ricalcola ore buche docenti
    res.gaps_by_teacher = {}
    for t_id, t_grid in res.grid_by_teacher.items():
        tot_g = 0
        for d in range(len(days)):
            H = daily_h[d]
            active_h = [hh for hh in range(H) if t_grid[d][hh] is not None]
            if len(active_h) >= 2:
                span = max(active_h) - min(active_h) + 1
                tot_g += (span - len(active_h))
        res.gaps_by_teacher[t_id] = tot_g

def find_smart_repair_proposals(
    problem: TimetableProblem,
    current_result: TimetableResult,
    target_class_id: str,
    target_day: int,
    target_hour: int,
    target_subject_id: str,
    orig_assignment_id: Optional[str] = None,
    max_proposals: int = 3,
    time_limit_sec: int = 8
) -> List[SwapProposal]:
    """Trova fino a max_proposals catene di riparazione minime per forzare la lezione al target_day/target_hour."""
    proposals: List[SwapProposal] = []
    
    days = getattr(problem.config, "active_days", None) or getattr(problem.config, "days", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])[:problem.config.num_days]
    daily_h = getattr(problem.config, "daily_hours", [6]*5)[:problem.config.num_days]
    
    # 1. Trova l'assegnazione esatta
    target_assign = None
    if orig_assignment_id:
        target_assign = next((a for a in problem.assignments if a.id == orig_assignment_id), None)
    if not target_assign:
        matching_assigns = [a for a in problem.assignments if a.class_id == target_class_id and (a.subject_id == target_subject_id or a.id == target_subject_id)]
        if matching_assigns:
            target_assign = matching_assigns[0]
            
    if not target_assign:
        return []
    
    # 2. Costruisci il modello CP-SAT di riparazione locale (LNS)
    solver = TimetableSolver(problem)
    solver.build_model(skip_penalties=False)
    
    m = solver.model
    # FORZA il vincolo desiderato dall'utente
    m.Add(solver.x[target_assign.id, target_day, target_hour] == 1)
    
    # 3. Inietta la soluzione attuale come Warm Start Hints e penalizza le deviazioni
    change_penalties = []
    for a in problem.assignments:
        c_id = a.class_id
        c_grid = current_result.grid_by_class.get(c_id, [])
        for d in range(len(days)):
            for h in range(daily_h[d]):
                curr_slot = c_grid[d][h] if d < len(c_grid) and h < len(c_grid[d]) else None
                # Considera attiva se corrisponde per assignment_id o per subject_id nella stessa classe
                curr_active = 1 if (curr_slot and (curr_slot.assignment_id == a.id or (curr_slot.class_id == a.class_id and curr_slot.subject_id == a.subject_id))) else 0
                
                # Aggiungi Hint di avvio caldo
                m.AddHint(solver.x[a.id, d, h], curr_active)
                
                # Variabile di deviazione: se lo stato cambia rispetto all'orario attuale, penalizza
                diff_var = m.NewBoolVar(f"diff_{a.id}_d{d}_h{h}")
                if curr_active == 1:
                    m.Add(solver.x[a.id, d, h] == 0).OnlyEnforceIf(diff_var)
                    m.Add(solver.x[a.id, d, h] == 1).OnlyEnforceIf(diff_var.Not())
                else:
                    m.Add(solver.x[a.id, d, h] == 1).OnlyEnforceIf(diff_var)
                    m.Add(solver.x[a.id, d, h] == 0).OnlyEnforceIf(diff_var.Not())
                change_penalties.append(diff_var)

    # Obiettivo Primario: Minimizzare gli spostamenti complessivi
    m.Minimize(sum(change_penalties) * 50000)
    
    # Risolutore CP-SAT veloce con parametri dedicati
    cp_solver = cp_model.CpSolver()
    cp_solver.parameters.max_time_in_seconds = time_limit_sec
    cp_solver.parameters.num_workers = 8
    cp_solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
    
    status = cp_solver.Solve(m)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        repaired_res = solver._extract_result(cp_solver, cp_solver.StatusName(status), cp_solver.WallTime(), cp_solver.ObjectiveValue())
        report = validate_timetable(problem, repaired_res)
        
        # Calcola i dettagli delle modifiche rispetto a current_result
        changes = []
        for c_id, c_grid in repaired_res.grid_by_class.items():
            old_grid = current_result.grid_by_class.get(c_id, [])
            c_name = problem.classes[c_id].name if c_id in problem.classes else c_id
            for d in range(len(days)):
                for h in range(daily_h[d]):
                    old_s = old_grid[d][h] if d < len(old_grid) and h < len(old_grid[d]) else None
                    new_s = c_grid[d][h] if d < len(c_grid) and h < len(c_grid[d]) else None
                    
                    old_id = old_s.subject_id if old_s else None
                    new_id = new_s.subject_id if new_s else None
                    
                    if old_id != new_id:
                        d_name = days[d]
                        h_str = f"{h+1}ª Ora"
                        sub_str = problem.subjects[new_id].name if new_id in problem.subjects else (new_id or "Ora Libera")
                        changes.append(f"Classe {c_name} · {d_name} {h_str} -> {sub_str}")

        num_changes = len(changes) // 2 if len(changes) > 0 else 1
        proposals.append(SwapProposal(
            proposal_id="prop_1",
            description=f"Riparazione Minima ({num_changes} spostamenti a catena)",
            changes_count=num_changes,
            resulting_result=repaired_res,
            report=report,
            changes_details=changes
        ))
        
    return proposals
