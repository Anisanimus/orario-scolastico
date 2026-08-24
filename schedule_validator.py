"""Modulo per la validazione deterministica e l'audit dei conflitti di un orario scolastico."""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from models import TimetableProblem
from solver import TimetableResult, LessonSlotInfo

SlotInfo = LessonSlotInfo

@dataclass
class ValidationIssue:
    issue_type: str # "ERROR" o "WARNING"
    category: str # "DOCENTE", "AULA", "CLASSE", "MONTE_ORE", "INDISPONIBILITA", "VINCOLO_GIORNALIERO"
    title: str
    description: str
    day_idx: Optional[int] = None
    hour_idx: Optional[int] = None
    day_name: Optional[str] = None
    hour_str: Optional[str] = None
    entities_involved: List[str] = field(default_factory=list)

@dataclass
class ValidationReport:
    is_valid: bool
    total_errors: int
    total_warnings: int
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

def validate_timetable(problem: TimetableProblem, result: TimetableResult) -> ValidationReport:
    """Esegue un audit completo di conformita e ricerca conflitti sull'orario generato o importato."""
    issues: List[ValidationIssue] = []
    days = getattr(problem.config, "active_days", None) or getattr(problem.config, "days", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])[:problem.config.num_days]
    daily_h = getattr(problem.config, "daily_hours", [6]*5)[:problem.config.num_days]
    
    # 1. VERIFICA SOVRAPPOSIZIONI DOCENTE & INDISPONIBILITA
    # teacher_id -> [d][h] -> list of SlotInfo
    teacher_schedule: Dict[str, List[List[List[SlotInfo]]]] = {
        t_id: [[[] for _ in range(daily_h[d])] for d in range(len(days))]
        for t_id in problem.teachers.keys()
    }
    
    # 2. VERIFICA SOVRAPPOSIZIONI AULA & CAPIENZA
    room_schedule: Dict[str, List[List[List[SlotInfo]]]] = {
        r_id: [[[] for _ in range(daily_h[d])] for d in range(len(days))]
        for r_id in problem.rooms.keys()
    }
    
    # 3. VERIFICA SOVRAPPOSIZIONI CLASSE & MONTE ORE
    class_assigned_hours: Dict[str, Dict[str, int]] = {
        c_id: {} for c_id in problem.classes.keys()
    }
    
    # Popolamento strutture da grid_by_class
    active_parallel_groups = [g for g in getattr(problem.config, "parallel_groups", []) if getattr(g, "is_active", True)]
    
    for c_id, c_grid in result.grid_by_class.items():
        c_obj = problem.classes.get(c_id)
        c_name = c_obj.name if c_obj else c_id
        
        for d in range(len(days)):
            for h in range(daily_h[d]):
                slot: Optional[SlotInfo] = c_grid[d][h] if d < len(c_grid) and h < len(c_grid[d]) else None
                if slot is None:
                    continue
                    
                sub_id = slot.subject_id
                class_assigned_hours[c_id][sub_id] = class_assigned_hours[c_id].get(sub_id, 0) + 1
                
                t_id = slot.teacher_id
                if t_id and t_id in teacher_schedule:
                    teacher_schedule[t_id][d][h].append(slot)
                    
                r_id = slot.room_id
                if r_id and r_id in room_schedule:
                    room_schedule[r_id][d][h].append(slot)
                    
    # Controllo Sovrapposizioni Docente
    for t_id, t_grid in teacher_schedule.items():
        t_obj = problem.teachers[t_id]
        t_name = t_obj.name
        
        for d in range(len(days)):
            d_name = days[d]
            for h in range(daily_h[d]):
                slots_at_h = t_grid[d][h]
                
                # Se il docente ha piu di 1 classe contemporaneamente:
                if len(slots_at_h) > 1:
                    # Verifica se si tratta di una classe aperta / parallelismo lecito
                    is_valid_parallel = False
                    first_sub = slots_at_h[0].subject_id
                    c_ids_in_slot = [s.class_id for s in slots_at_h]
                    
                    for grp in active_parallel_groups:
                        if grp.subject_id == first_sub and all(cid in grp.class_ids for cid in c_ids_in_slot):
                            is_valid_parallel = True
                            break
                            
                    if not is_valid_parallel:
                        class_names = [problem.classes[s.class_id].name if s.class_id in problem.classes else s.class_id for s in slots_at_h]
                        issues.append(ValidationIssue(
                            issue_type="ERROR",
                            category="DOCENTE",
                            title=f"Sovrapposizione Docente: {t_name}",
                            description=f"Il docente {t_name} risulta assegnato contemporaneamente a {len(slots_at_h)} classi ({', '.join(class_names)}) il {d_name} alla {h+1}ª ora.",
                            day_idx=d,
                            hour_idx=h,
                            day_name=d_name,
                            hour_str=f"{h+1}ª Ora",
                            entities_involved=[t_id] + [s.class_id for s in slots_at_h]
                        ))
                        
                # Controllo Indisponibilita Docente
                if slots_at_h and [d, h] in t_obj.unavailable_slots:
                    issues.append(ValidationIssue(
                        issue_type="ERROR",
                        category="INDISPONIBILITA",
                        title=f"Violazione Indisponibilita: {t_name}",
                        description=f"Il docente {t_name} ha lezione il {d_name} alla {h+1}ª ora, ma lo slot e contrassegnato come indisponibile/bloccato.",
                        day_idx=d,
                        hour_idx=h,
                        day_name=d_name,
                        hour_str=f"{h+1}ª Ora",
                        entities_involved=[t_id]
                    ))
                    
            # Controllo Giorno Libero Forzato
            if d_name in t_obj.free_days:
                day_slots = sum(len(t_grid[d][hh]) for hh in range(daily_h[d]))
                if day_slots > 0:
                    issues.append(ValidationIssue(
                        issue_type="WARNING",
                        category="DOCENTE",
                        title=f"Mancato Giorno Libero: {t_name}",
                        description=f"Il docente {t_name} ha {day_slots} ore di lezione il {d_name}, che era indicato tra i giorni liberi preferiti.",
                        day_idx=d,
                        day_name=d_name,
                        entities_involved=[t_id]
                    ))
                    
            # Controllo Massimo Ore Giornaliere Docente
            active_hours_today = sum(1 for hh in range(daily_h[d]) if t_grid[d][hh])
            max_d = getattr(t_obj, "max_daily_hours", 5) or 5
            if active_hours_today > max_d:
                issues.append(ValidationIssue(
                    issue_type="WARNING",
                    category="VINCOLO_GIORNALIERO",
                    title=f"Supero Ore Giornaliere: {t_name}",
                    description=f"Il docente {t_name} insegna {active_hours_today} ore il {d_name} (limite massimo impostato: {max_d}h).",
                    day_idx=d,
                    day_name=d_name,
                    entities_involved=[t_id]
                ))

    # Controllo Sovrapposizioni Aule e Capienza
    for r_id, r_grid in room_schedule.items():
        r_obj = problem.rooms[r_id]
        r_name = r_obj.name
        cap = getattr(r_obj, "capacity", 1) or 1
        
        for d in range(len(days)):
            d_name = days[d]
            for h in range(daily_h[d]):
                slots_in_room = r_grid[d][h]
                if len(slots_in_room) > cap:
                    # Verifica se e un gruppo parallelo che condivide l'aula
                    is_shared_parallel = False
                    first_sub = slots_in_room[0].subject_id
                    c_ids_in_room = [s.class_id for s in slots_in_room]
                    for grp in active_parallel_groups:
                        if grp.subject_id == first_sub and all(cid in grp.class_ids for cid in c_ids_in_room):
                            is_shared_parallel = True
                            break
                            
                    if not is_shared_parallel:
                        class_names = [problem.classes[s.class_id].name if s.class_id in problem.classes else s.class_id for s in slots_in_room]
                        issues.append(ValidationIssue(
                            issue_type="ERROR",
                            category="AULA",
                            title=f"Sovraffollamento Aula: {r_name}",
                            description=f"L'aula/laboratorio {r_name} ospita contemporaneamente {len(slots_in_room)} classi ({', '.join(class_names)}) il {d_name} alla {h+1}ª ora (capienza massima: {cap}).",
                            day_idx=d,
                            hour_idx=h,
                            day_name=d_name,
                            hour_str=f"{h+1}ª Ora",
                            entities_involved=[r_id] + [s.class_id for s in slots_in_room]
                        ))

    # Controllo Monte Ore Assegnato vs Piano di Studi
    for a in problem.assignments:
        c_id = a.class_id
        sub_id = a.subject_id
        assigned_h = class_assigned_hours.get(c_id, {}).get(sub_id, 0)
        c_name = problem.classes[c_id].name if c_id in problem.classes else c_id
        sub_name = problem.subjects[sub_id].name if sub_id in problem.subjects else sub_id
        
        if assigned_h != a.hours_per_week:
            diff = assigned_h - a.hours_per_week
            diff_str = f"+{diff}h in eccesso" if diff > 0 else f"{abs(diff)}h mancanti"
            issues.append(ValidationIssue(
                issue_type="ERROR",
                category="MONTE_ORE",
                title=f"Discrepanza Monte Ore: {c_name} - {sub_name}",
                description=f"Per la classe {c_name} in {sub_name} risultano posizionate {assigned_h} ore su {a.hours_per_week}h previste ({diff_str}).",
                entities_involved=[c_id, sub_id]
            ))

    total_errors = sum(1 for iss in issues if iss.issue_type == "ERROR")
    total_warnings = sum(1 for iss in issues if iss.issue_type == "WARNING")
    
    return ValidationReport(
        is_valid=(total_errors == 0),
        total_errors=total_errors,
        total_warnings=total_warnings,
        issues=issues,
        stats={
            "total_classes": len(problem.classes),
            "total_teachers": len(problem.teachers),
            "total_rooms": len(problem.rooms)
        }
    )
