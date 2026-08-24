# Modulo di Risoluzione per l'Orario dei Docenti di Sostegno e Potenziamento.
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Set
import time
import math
from ortools.sat.python import cp_model

from models import (
    TimetableProblem,
    DAYS_OF_WEEK,
    StudentDVA,
    SupportAssignment,
    EnhancementAssignment,
    Teacher
)
from solver import TimetableResult, LessonSlotInfo

@dataclass
class SupportSlotInfo:
    assignment_id: str
    teacher_id: str
    teacher_name: str
    class_id: str
    class_name: str
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    is_severe: bool = False
    curricular_subject_id: str = ''
    curricular_subject_name: str = ''
    curricular_teacher_name: str = ''
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    is_enhancement: bool = False
    activity_type: str = 'sostegno'

    @property
    def subject_id(self) -> str:
        return self.curricular_subject_id

    @property
    def subject_name(self) -> str:
        return self.curricular_subject_name

@dataclass
class SupportTimetableResult:
    status: str
    solve_time: float = 0.0
    
    grid_by_support_teacher: Dict[str, List[List[List[SupportSlotInfo]]]] = field(default_factory=dict)
    grid_by_class_support: Dict[str, List[List[List[SupportSlotInfo]]]] = field(default_factory=dict)
    grid_by_student_dva: Dict[str, List[List[Optional[SupportSlotInfo]]]] = field(default_factory=dict)
    class_coverage_report: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    teacher_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    total_assigned_hours: int = 0
    total_covered_slots: int = 0
    total_simultaneous_hours: int = 0

def auto_assign_support_chairs(problem: TimetableProblem) -> Tuple[bool, str]:
    """
    Abbinamento automatico intelligente dei casi DVA e delle classi ai docenti di sostegno.
    Regole di ottimizzazione:
    1. Quadratura perfetta delle 18h (o contratto part-time) per ciascun docente.
    2. Minimizzazione della frammentazione: un docente segue al massimo 2 classi (es. 1 caso da 18h o 2 casi da 9h).
    3. Vicinanza di sezione/plesso: favorisce abbinamento di alunni della stessa classe o sezione.
    4. Priorità Casi Gravi (1:1): assegnati a cattedre intere.
    """
    sos_teachers = {
        t_id: t for t_id, t in problem.teachers.items() 
        if "sostegno" in getattr(t, "cdc", "").lower() or "admm" in getattr(t, "cdc", "").lower() or "sostegno" in t.name.lower()
    }
    
    if not sos_teachers:
        return False, "Nessun docente di sostegno trovato nell'organico (CdC ADMM / Sostegno)."
        
    if not problem.students_dva:
        return False, "Nessun alunno DVA registrato."

    tot_dva_hours = sum(s.weekly_hours for s in problem.students_dva.values())
    tot_teacher_hours = sum(getattr(t, "contract_hours", 18) or 18 for t in sos_teachers.values())
    
    m = cp_model.CpModel()
    x = {}
    
    for s_id in problem.students_dva.keys():
        for t_id in sos_teachers.keys():
            x[s_id, t_id] = m.NewBoolVar(f"x_{s_id}_{t_id}")
            
    for s_id in problem.students_dva.keys():
        m.Add(sum(x[s_id, t_id] for t_id in sos_teachers.keys()) == 1)
        
    penalties = []
    for t_id, t in sos_teachers.items():
        t_target = getattr(t, "contract_hours", 18) or 18
        assigned_h = sum(x[s_id, t_id] * problem.students_dva[s_id].weekly_hours for s_id in problem.students_dva.keys())
        m.Add(assigned_h <= t_target)
        penalties.append((t_target - assigned_h) * 1000)
        
        num_studs = sum(x[s_id, t_id] for s_id in problem.students_dva.keys())
        m.Add(num_studs <= 3)
        penalties.append(num_studs * 10)

    for t_id in sos_teachers.keys():
        stud_list = list(problem.students_dva.values())
        for i in range(len(stud_list)):
            for j in range(i + 1, len(stud_list)):
                s1 = stud_list[i]
                s2 = stud_list[j]
                if s1.class_id == s2.class_id:
                    together = m.NewBoolVar(f"tog_{t_id}_{s1.id}_{s2.id}")
                    m.Add(together <= x[s1.id, t_id])
                    m.Add(together <= x[s2.id, t_id])
                    m.Add(together >= x[s1.id, t_id] + x[s2.id, t_id] - 1)
                    penalties.append(together.Not() * 200)

    if penalties:
        m.Minimize(sum(penalties))
        
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    status = solver.Solve(m)
    
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return False, f"Impossibile quadrare le ore degli alunni ({tot_dva_hours}h) con i docenti ({tot_teacher_hours}h). Verifica i contratti."
        
    new_assignments = []
    for s_id, s in problem.students_dva.items():
        for t_id in sos_teachers.keys():
            if solver.Value(x[s_id, t_id]) == 1:
                new_assignments.append(SupportAssignment(
                    id=f"sa_{t_id}_{s.class_id}_{s_id}",
                    teacher_id=t_id,
                    student_id=s_id,
                    class_id=s.class_id,
                    hours_per_week=s.weekly_hours,
                    preferred_subject_ids=s.preferred_subjects
                ))
                
    problem.support_assignments = new_assignments
    return True, f"Abbinate con successo {len(new_assignments)} cattedre di sostegno per {tot_dva_hours} ore totali!"


class SupportTimetableSolver:
    def __init__(self, problem: TimetableProblem, curricular_result: Optional[TimetableResult] = None):
        self.problem = problem
        self.curricular_result = curricular_result
        self.num_days = problem.config.num_days
        self.daily_hours = problem.config.daily_hours[:self.num_days]
        self.model = cp_model.CpModel()
        self.y = {}
        self.z = {}

    def solve(self, max_time_seconds: int = 15) -> SupportTimetableResult:
        start_time = time.time()
        
        if not self.curricular_result or not self.curricular_result.grid_by_class:
            return SupportTimetableResult(
                status='NO_CURRICULAR_SCHEDULE',
                solve_time=0.0
            )

        prob = self.problem
        num_days = self.num_days
        daily_hours = self.daily_hours
        m = self.model
        penalties = []

        for sa in prob.support_assignments:
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    self.y[sa.id, d, h] = m.NewBoolVar(f'y_{sa.id}_{d}_{h}')

        for ea in prob.enhancement_assignments:
            target_classes = ea.target_class_ids or list(prob.classes.keys())
            for c_id in target_classes:
                for d in range(num_days):
                    for h in range(daily_hours[d]):
                        self.z[ea.id, c_id, d, h] = m.NewBoolVar(f'z_{ea.id}_{c_id}_{d}_{h}')

        for sa in prob.support_assignments:
            all_slots = [self.y[sa.id, d, h] for d in range(num_days) for h in range(daily_hours[d])]
            m.Add(sum(all_slots) == sa.hours_per_week)

        for ea in prob.enhancement_assignments:
            target_classes = ea.target_class_ids or list(prob.classes.keys())
            all_pot_slots = [self.z[ea.id, c_id, d, h] for c_id in target_classes for d in range(num_days) for h in range(daily_hours[d])]
            m.Add(sum(all_pot_slots) <= ea.hours_per_week)

        for t_id, teacher in prob.teachers.items():
            t_sa = [sa for sa in prob.support_assignments if sa.teacher_id == t_id]
            t_ea = [ea for ea in prob.enhancement_assignments if ea.teacher_id == t_id]
            
            if not t_sa and not t_ea:
                continue

            contract_h = getattr(teacher, 'contract_hours', None) or (9 if getattr(teacher, 'is_part_time', False) else 18)
            is_pt = getattr(teacher, 'is_part_time', False) or contract_h < 15
            max_d_h = getattr(teacher, 'max_daily_hours', 5) or 5
            max_cons = getattr(teacher, 'max_consecutive_hours', 4) or 4
            min_d_h = getattr(teacher, 'min_daily_hours', 2) or 2
            eff_min_d = min(min_d_h, contract_h) if contract_h > 0 else 0

            day_active_vars = []
            u_vars = {} # (d, h) -> BoolVar

            for d in range(num_days):
                H = daily_hours[d]
                day_terms = []
                
                for h in range(H):
                    sa_terms = [self.y[sa.id, d, h] for sa in t_sa]
                    ea_terms = [self.z[ea.id, c_id, d, h] for ea in t_ea for c_id in (ea.target_class_ids or list(prob.classes.keys())) if (ea.id, c_id, d, h) in self.z]
                    
                    slot_sum = sum(sa_terms + ea_terms)
                    m.Add(slot_sum <= 1)
                    
                    uh = m.NewBoolVar(f'uh_{t_id}_{d}_{h}')
                    m.Add(uh == slot_sum)
                    u_vars[d, h] = uh
                    day_terms.append(uh)

                # Massimo ore giornaliere (default max 5 ore)
                m.Add(sum(day_terms) <= max_d_h)

                # Massimo 4 ore consecutive di seguito (mai 5 ore continue)
                if max_cons < H:
                    w_size = max_cons + 1
                    for h in range(H - max_cons):
                        m.Add(sum(u_vars[d, h + k] for k in range(w_size)) <= max_cons)

                # Variabile giorno attivo
                da = m.NewBoolVar(f'da_sup_{t_id}_{d}')
                m.Add(sum(day_terms) <= max_d_h * da)
                if eff_min_d > 0:
                    m.Add(sum(day_terms) >= eff_min_d * da)

                day_active_vars.append(da)

                # Indisponibilità orarie e giorni liberi
                for slot in getattr(teacher, 'unavailable_slots', []):
                    if len(slot) == 2 and slot[0] == d and slot[1] < H:
                        m.Add(u_vars[d, slot[1]] == 0)

                # Giorno libero esplicito
                free_days = getattr(teacher, 'free_days', [])
                if d < len(DAYS_OF_WEEK) and DAYS_OF_WEEK[d] in free_days:
                    m.Add(da == 0)

                # Calcolo buchi orari (Gaps) per il docente di sostegno
                for h in range(1, H - 1):
                    has_earlier = m.NewBoolVar(f'he_{t_id}_{d}_{h}')
                    has_later = m.NewBoolVar(f'hl_{t_id}_{d}_{h}')
                    
                    earlier_slots = [u_vars[d, k] for k in range(h)]
                    later_slots = [u_vars[d, k] for k in range(h + 1, H)]
                    
                    for es in earlier_slots:
                        m.Add(has_earlier >= es)
                    m.Add(has_earlier <= sum(earlier_slots))
                    
                    for ls in later_slots:
                        m.Add(has_later >= ls)
                    m.Add(has_later <= sum(later_slots))
                    
                    gap_h = m.NewBoolVar(f'gap_sup_{t_id}_{d}_{h}')
                    m.Add(gap_h >= has_earlier + has_later - 1 - u_vars[d, h])
                    m.Add(gap_h <= has_earlier)
                    m.Add(gap_h <= has_later)
                    m.Add(gap_h <= 1 - u_vars[d, h])
                    penalties.append(gap_h * 2000)

            # Spalmatura sui giorni
            if not is_pt:
                if num_days == 5:
                    # Tempo pieno 18h su 5 giorni: spalmato esattamente su 5 giorni lavorativi (es. 4-4-4-3-3)
                    m.Add(sum(day_active_vars) == 5)
                elif num_days == 6:
                    # Tempo pieno 18h su 6 giorni: massimo 5 giorni lavorativi (1 giorno libero)
                    m.Add(sum(day_active_vars) <= 5)
                    m.Add(sum(day_active_vars) >= 4)
            else:
                max_w_d = getattr(teacher, 'max_working_days', 3) or 3
                m.Add(sum(day_active_vars) <= min(max_w_d, num_days))
                m.Add(sum(day_active_vars) >= 2)

        for ea in prob.enhancement_assignments:
            target_classes = ea.target_class_ids or list(prob.classes.keys())
            for c_id in target_classes:
                for d in range(num_days):
                    for h in range(daily_hours[d]):
                        cell = None
                        if c_id in self.curricular_result.grid_by_class:
                            if d < len(self.curricular_result.grid_by_class[c_id]) and h < len(self.curricular_result.grid_by_class[c_id][d]):
                                cell = self.curricular_result.grid_by_class[c_id][d][h]
                        
                        if ea.subject_id and ea.subject_id != 'tutte':
                            if not cell or getattr(cell, 'subject_id', '') != ea.subject_id:
                                m.Add(self.z[ea.id, c_id, d, h] == 0)

        for ea in prob.enhancement_assignments:
            target_classes = ea.target_class_ids or list(prob.classes.keys())
            all_pot_slots = [self.z[ea.id, c_id, d, h] for c_id in target_classes for d in range(num_days) for h in range(daily_hours[d])]
            penalties.append((ea.hours_per_week - sum(all_pot_slots)) * 20000)

        # =============================================================
        # 1. VINCOLI ALUNNO DVA (Unicità e Distribuzione Omogenea)
        # =============================================================
        for s_id, stud in prob.students_dva.items():
            stud_sa = [sa for sa in prob.support_assignments if sa.student_id == s_id]
            if not stud_sa:
                continue
            
            stud_tot_h = sum(sa.hours_per_week for sa in stud_sa)
            
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    # HARD CONSTRAINT: Mai più di 1 docente sullo stesso alunno nella stessa ora!
                    m.Add(sum(self.y[sa.id, d, h] for sa in stud_sa) <= 1)

                # Bilanciamento giornaliero per alunno
                day_stud_terms = [self.y[sa.id, d, h] for sa in stud_sa for h in range(daily_hours[d])]
                max_daily_stud = min(daily_hours[d], math.ceil(stud_tot_h / num_days) + 1)
                m.Add(sum(day_stud_terms) <= max_daily_stud)
                if stud_tot_h >= 15 and num_days == 5:
                    m.Add(sum(day_stud_terms) >= 2)

        # =============================================================
        # 2. VINCOLI CLASSE (Niente assembramenti di 3 o 4 docenti, Copertura Completa)
        # =============================================================
        for c_id, c in prob.classes.items():
            c_sa = [sa for sa in prob.support_assignments if sa.class_id == c_id]
            if not c_sa:
                continue

            tot_c_hours = sum(sa.hours_per_week for sa in c_sa)
            tot_c_weekly_slots = sum(daily_hours[:num_days])
            studs_in_c = set(sa.student_id for sa in c_sa if sa.student_id)
            num_studs_in_c = len(studs_in_c)
            
            # Limite massimo contemporaneo:
            # Se 1 alunno -> max 1 docente
            # Se >=2 alunni -> max 2 docenti (MAI 3 o 4 docenti nella stessa classe e stessa ora!)
            max_simultaneous = min(2, num_studs_in_c)

            prio_double_subs = getattr(prob.config, "support_priority_subjects_double_coverage", ["ita", "mat", "sci", "ing", "tec"]) or []
            
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    slot_terms = [self.y[sa.id, d, h] for sa in c_sa]
                    
                    # HARD CONSTRAINT: massimo 2 docenti di sostegno presenti (se >=2 alunni) o 1 docente (se 1 alunno)
                    m.Add(sum(slot_terms) <= max_simultaneous)

                    if tot_c_hours <= tot_c_weekly_slots:
                        # Se il fabbisogno di sostegno è <= alle ore della classe (es. 18h <= 30h)
                        # NON serve alcuna compresenza: max 1 docente per ora!
                        m.Add(sum(slot_terms) <= 1)
                    else:
                        # Se tot_c_hours > 30h (es. 36h con 2 alunni):
                        # TUTTE le 30 ore della classe DEVONO avere almeno 1 docente di sostegno (zero ore scoperte!)
                        m.Add(sum(slot_terms) >= 1)
                        
                        # Recupera la materia curricolare di questa specifica ora
                        curr_cell = None
                        if c_id in self.curricular_result.grid_by_class:
                            if d < len(self.curricular_result.grid_by_class[c_id]) and h < len(self.curricular_result.grid_by_class[c_id][d]):
                                curr_cell = self.curricular_result.grid_by_class[c_id][d][h]
                        curr_subj_id = getattr(curr_cell, 'subject_id', '') if curr_cell else ''

                        is_double = m.NewBoolVar(f'double_sup_{c_id}_{d}_{h}')
                        m.Add(sum(slot_terms) == 2).OnlyEnforceIf(is_double)
                        m.Add(sum(slot_terms) <= 1).OnlyEnforceIf(is_double.Not())
                        
                        # Se la materia è tra quelle prioritarie per la doppia presenza (es. Ita, Mat, Sci, Ing, Tec), favorita con forza!
                        if curr_subj_id and curr_subj_id in prio_double_subs:
                            penalties.append(is_double * 100) # Penalità minima -> massimizza contemporaneità su queste materie
                        else:
                            penalties.append(is_double * 3500) # Forte penalità altrove

        # =============================================================
        # 3. PREFERENZE DIDATTICHE & DESIDERATA
        # =============================================================
        for sa in prob.support_assignments:
            stud = prob.students_dva.get(sa.student_id) if sa.student_id else None
            c_id = sa.class_id
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    cell = None
                    if c_id in self.curricular_result.grid_by_class:
                        if d < len(self.curricular_result.grid_by_class[c_id]) and h < len(self.curricular_result.grid_by_class[c_id][d]):
                            cell = self.curricular_result.grid_by_class[c_id][d][h]
                    
                    s_id = getattr(cell, 'subject_id', '') if cell else ''
                    
                    if stud:
                        if stud.is_severe_coverage:
                            penalties.append(self.y[sa.id, d, h].Not() * 300)
                        if s_id and s_id in stud.preferred_subjects:
                            penalties.append(self.y[sa.id, d, h].Not() * 200)
                        if s_id and s_id in stud.excluded_subjects:
                            penalties.append(self.y[sa.id, d, h] * 1000)
                        if stud.preferred_hours and h in stud.preferred_hours:
                            penalties.append(self.y[sa.id, d, h].Not() * 100)

                    # Desiderata didattici del docente di sostegno (aree / materie preferite)
                    t_obj = prob.teachers.get(sa.teacher_id)
                    t_pref_subs = list(sa.preferred_subject_ids or [])
                    if t_obj and getattr(t_obj, 'preferred_areas', None):
                        from models import DISCIPLINARY_AREAS
                        for area_k in t_obj.preferred_areas:
                            if area_k in DISCIPLINARY_AREAS:
                                t_pref_subs.extend(DISCIPLINARY_AREAS[area_k]["subjects"])
                    t_pref_subs = list(set(t_pref_subs))

                    if s_id and s_id in t_pref_subs:
                        penalties.append(self.y[sa.id, d, h].Not() * 250)

        if penalties:
            m.Minimize(sum(penalties))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time_seconds
        solver.parameters.num_workers = 8
        solver.parameters.cp_model_presolve = True
        
        status_code = solver.Solve(m)
        status_map = {
            cp_model.OPTIMAL: 'OPTIMAL',
            cp_model.FEASIBLE: 'FEASIBLE',
            cp_model.INFEASIBLE: 'INFEASIBLE',
            cp_model.MODEL_INVALID: 'INVALID',
            cp_model.UNKNOWN: 'UNKNOWN'
        }
        status_str = status_map.get(status_code, 'UNKNOWN')
        elapsed = time.time() - start_time
        
        res = SupportTimetableResult(
            status=status_str,
            solve_time=round(elapsed, 2)
        )
        
        if status_str not in ['OPTIMAL', 'FEASIBLE']:
            return res

        for t_id in prob.teachers.keys():
            res.grid_by_support_teacher[t_id] = [[[] for _ in range(daily_hours[d])] for d in range(num_days)]
            
        for c_id in prob.classes.keys():
            res.grid_by_class_support[c_id] = [[[] for _ in range(daily_hours[d])] for d in range(num_days)]
            
        for s_id in prob.students_dva.keys():
            res.grid_by_student_dva[s_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]

        for sa in prob.support_assignments:
            t = prob.teachers.get(sa.teacher_id)
            c = prob.classes.get(sa.class_id)
            stud = prob.students_dva.get(sa.student_id) if sa.student_id else None
            
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    if solver.Value(self.y[sa.id, d, h]) == 1:
                        res.total_assigned_hours += 1
                        
                        cur_cell = None
                        if sa.class_id in self.curricular_result.grid_by_class:
                            if d < len(self.curricular_result.grid_by_class[sa.class_id]) and h < len(self.curricular_result.grid_by_class[sa.class_id][d]):
                                cur_cell = self.curricular_result.grid_by_class[sa.class_id][d][h]
                                
                        slot_info = SupportSlotInfo(
                            assignment_id=sa.id,
                            teacher_id=sa.teacher_id,
                            teacher_name=t.name if t else sa.teacher_id,
                            class_id=sa.class_id,
                            class_name=c.name if c else sa.class_id,
                            student_id=sa.student_id,
                            student_name=stud.name if stud else '',
                            is_severe=stud.is_severe_coverage if stud else False,
                            curricular_subject_id=getattr(cur_cell, 'subject_id', ''),
                            curricular_subject_name=getattr(cur_cell, 'subject_name', ''),
                            curricular_teacher_name=getattr(cur_cell, 'teacher_name', ''),
                            room_id=getattr(cur_cell, 'room_id', None) if cur_cell else None,
                            room_name=getattr(cur_cell, 'room_name', None) if cur_cell else None,
                            is_enhancement=False,
                            activity_type='sostegno'
                        )
                        
                        res.grid_by_support_teacher[sa.teacher_id][d][h].append(slot_info)
                        res.grid_by_class_support[sa.class_id][d][h].append(slot_info)
                        if sa.student_id and sa.student_id in res.grid_by_student_dva:
                            res.grid_by_student_dva[sa.student_id][d][h] = slot_info

        for ea in prob.enhancement_assignments:
            t = prob.teachers.get(ea.teacher_id)
            target_classes = ea.target_class_ids or list(prob.classes.keys())
            for c_id in target_classes:
                c = prob.classes.get(c_id)
                for d in range(num_days):
                    for h in range(daily_hours[d]):
                        if (ea.id, c_id, d, h) in self.z and solver.Value(self.z[ea.id, c_id, d, h]) == 1:
                            cur_cell = None
                            if c_id in self.curricular_result.grid_by_class:
                                if d < len(self.curricular_result.grid_by_class[c_id]) and h < len(self.curricular_result.grid_by_class[c_id][d]):
                                    cur_cell = self.curricular_result.grid_by_class[c_id][d][h]
                                    
                            slot_info = SupportSlotInfo(
                                assignment_id=ea.id,
                                teacher_id=ea.teacher_id,
                                teacher_name=t.name if t else ea.teacher_id,
                                class_id=c_id,
                                class_name=c.name if c else c_id,
                                student_id=None,
                                student_name=None,
                                is_severe=False,
                                curricular_subject_id=getattr(cur_cell, 'subject_id', ''),
                                curricular_subject_name=getattr(cur_cell, 'subject_name', ''),
                                curricular_teacher_name=getattr(cur_cell, 'teacher_name', ''),
                                room_id=getattr(cur_cell, 'room_id', None) if cur_cell else None,
                                room_name=getattr(cur_cell, 'room_name', None) if cur_cell else None,
                                is_enhancement=True,
                                activity_type=ea.activity_type
                            )
                            res.grid_by_support_teacher[ea.teacher_id][d][h].append(slot_info)
                            res.grid_by_class_support[c_id][d][h].append(slot_info)

        for c_id, c in prob.classes.items():
            tot_slots = sum(daily_hours[:num_days])
            covered = 0
            simultaneous = 0
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    occupants = res.grid_by_class_support[c_id][d][h]
                    if len(occupants) >= 1:
                        covered += 1
                    if len(occupants) >= 2:
                        simultaneous += 1
                        
            uncovered = tot_slots - covered
            assigned_c_h = sum(sa.hours_per_week for sa in prob.support_assignments if sa.class_id == c_id)
            cov_pct = round(covered / tot_slots * 100, 1) if tot_slots > 0 else 100.0
            
            res.class_coverage_report[c_id] = {
                'class_name': c.name,
                'total_slots': tot_slots,
                'assigned_support_hours': assigned_c_h,
                'covered_hours': covered,
                'uncovered_hours': uncovered,
                'simultaneous_hours': simultaneous,
                'coverage_pct': cov_pct
            }
            res.total_covered_slots += covered
            res.total_simultaneous_hours += simultaneous

        # Calcolo statistiche analitiche e rispetto desiderata didattici per ciascun docente di sostegno
        from models import DISCIPLINARY_AREAS
        for t_id, t in prob.teachers.items():
            if t_id not in res.grid_by_support_teacher:
                continue
            
            p_areas = getattr(t, 'preferred_areas', []) or []
            p_area_labels = [DISCIPLINARY_AREAS[k]['label'] for k in p_areas if k in DISCIPLINARY_AREAS]
            
            p_subs = []
            for a_k in p_areas:
                if a_k in DISCIPLINARY_AREAS:
                    p_subs.extend(DISCIPLINARY_AREAS[a_k]['subjects'])
            p_subs = list(set(p_subs))
            
            grid_t = res.grid_by_support_teacher[t_id]
            tot_assigned = 0
            matched_preferred = 0
            subj_counts = {}
            daily_hours_list = [0] * num_days
            
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    slots = grid_t[d][h]
                    for sl in slots:
                        tot_assigned += 1
                        daily_hours_list[d] += 1
                        sub_id = getattr(sl, 'curricular_subject_id', '') or ''
                        sub_name = getattr(sl, 'curricular_subject_name', '') or sub_id.upper() or 'N.D.'
                        subj_counts[sub_name] = subj_counts.get(sub_name, 0) + 1
                        
                        if sub_id and (sub_id in p_subs or not p_subs):
                            matched_preferred += 1
                            
            active_days = sum(1 for dc in daily_hours_list if dc > 0)
            didactic_pct = round(matched_preferred / tot_assigned * 100) if tot_assigned > 0 else 100
            
            # Calcolo ore buche reali
            gap_hours_count = 0
            for d in range(num_days):
                active_h = [h for h in range(daily_hours[d]) if grid_t[d][h]]
                if len(active_h) >= 2:
                    min_h, max_h = min(active_h), max(active_h)
                    for h_chk in range(min_h + 1, max_h):
                        if not grid_t[d][h_chk]:
                            gap_hours_count += 1
            
            res.teacher_stats[t_id] = {
                'teacher_name': t.name,
                'is_part_time': getattr(t, 'is_part_time', False),
                'total_hours': tot_assigned,
                'active_days': active_days,
                'daily_hours_distribution': daily_hours_list,
                'max_daily_hours': max(daily_hours_list) if daily_hours_list else 0,
                'gap_hours': gap_hours_count,
                'preferred_areas': p_areas,
                'preferred_area_labels': p_area_labels,
                'preferred_subjects': p_subs,
                'matched_preferred_hours': matched_preferred,
                'didactic_pct': didactic_pct,
                'subject_hours_breakdown': subj_counts
            }

        return res
