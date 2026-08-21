"""
Motore di Risoluzione per l'Orario Scolastico basato su Google OR-Tools (CP-SAT).
Supporta modello Tradizionale e modello DADA con gestione completa di desiderata avanzati:
giorno libero, entrare tardi, uscire presto, slot puntuali sconsigliati, ore doppie e riduzione buchi.
"""
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from ortools.sat.python import cp_model
from models import TimetableProblem, DAYS_OF_WEEK, TeachingAssignment, Teacher, Classroom

@dataclass
class LessonSlotInfo:
    assignment_id: str
    class_id: str
    class_name: str
    teacher_id: str
    teacher_name: str
    subject_id: str
    subject_name: str
    subject_color: str
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    is_double: bool = False
    co_teachers: List[str] = field(default_factory=list) # Docenti in compresenza su questa cattedra
    parallel_classes: List[str] = field(default_factory=list) # Altre classi in contemporanea / classi aperte
    parallel_teachers: List[str] = field(default_factory=list) # Altri docenti in contemporanea
    is_compresenza: bool = False # True se presente compresenza o classi aperte
    compresenza_text: str = "" # Descrizione chiara (es. "Compresenza con 1D (Prof. Vitale)")

@dataclass
class TimetableResult:
    status: str  # "OPTIMAL", "FEASIBLE", "INFEASIBLE", "NOT_SOLVED"
    solve_time: float = 0.0
    objective_value: float = 0.0
    
    # [class_id][day_idx][hour_idx] -> LessonSlotInfo or None
    grid_by_class: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)
    
    # [teacher_id][day_idx][hour_idx] -> LessonSlotInfo or None
    grid_by_teacher: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)

    # [room_id][day_idx][hour_idx] -> LessonSlotInfo or None (Griglia occupazione Aule)
    grid_by_room: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)
    
    # Statistiche Desiderata
    total_gap_hours: int = 0
    gaps_by_teacher: Dict[str, int] = field(default_factory=dict)
    free_days_satisfied_first: int = 0
    free_days_total_first: int = 0
    free_days_satisfied_second: int = 0
    free_days_total_second: int = 0
    double_hours_satisfied: int = 0
    double_hours_total: int = 0
    double_hours_by_subject: Dict[str, Dict[str, Any]] = field(default_factory=dict) # Dettaglio per materia flaggata
    
    # Desiderata Avanzati
    soft_slots_satisfied: int = 0
    soft_slots_total: int = 0
    late_entry_satisfied: int = 0
    late_entry_total: int = 0
    early_exit_satisfied: int = 0
    early_exit_total: int = 0
    
    # Report Dettagliato per Docente ("Chi ho soddisfatto e chi no")
    teacher_reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    global_satisfaction_score: float = 100.0
    
    log_messages: List[str] = field(default_factory=list)

def diagnose_problem_feasibility(problem: TimetableProblem) -> List[str]:
    """Analizza a fondo la configurazione e restituisce una lista dettagliata e specifica di eventuali incongruenze, conflitti o colli di bottiglia nei dati."""
    issues = []
    tot_slots = problem.config.total_weekly_slots
    num_days = problem.config.num_days
    daily_hours = problem.config.daily_hours[:num_days]
    
    # 1. Controllo Monte Ore Classi (Tassativo 30h esatte o totale slot settimanali)
    for c_id, c in problem.classes.items():
        c_h = sum(a.hours_per_week for a in problem.assignments if a.class_id == c_id)
        if c_h != tot_slots:
            diff = c_h - tot_slots
            if diff > 0:
                issues.append(f"❌ **Classe {c.name}**: ha **{c_h} ore settimanali** (+{diff}h in eccesso rispetto alle {tot_slots}h previste).")
            else:
                issues.append(f"❌ **Classe {c.name}**: ha **{c_h} ore settimanali** (mancano {-diff}h per raggiungere le {tot_slots}h previste).")

    # 2. Controllo Part-Time, Disponibilità e Indisponibilità Docenti
    for t_id, t in problem.teachers.items():
        t_assignments = [a for a in problem.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
        t_h = sum(a.hours_per_week for a in t_assignments)
        unavail = len(getattr(t, "unavailable_slots", []))
        free_slots = tot_slots - unavail
        
        # A. Cattedra superiore alle ore feriali residue disponibili
        if t_h > free_slots:
            issues.append(f"❌ **Docente {t.name}**: cattedra da **{t_h} ore** ma con **{unavail} ore di indisponibilità tassativa** (restano solo {free_slots} ore utili su {tot_slots}h).")

        # B. Incompatibilità Part-Time su Giorni Massimi e Carico Giornaliero
        if t.is_part_time and t.max_working_days is not None:
            max_d = max(1, t.max_working_days)
            max_h_day = getattr(t, "max_daily_hours", 5) or 5
            max_pt_cap = max_d * max_h_day
            if t_h > max_pt_cap:
                min_days_needed = (t_h + max_h_day - 1) // max_h_day
                issues.append(f"❌ **Docente Part-Time {t.name}**: cattedra da **{t_h}h** assegnata su max **{max_d} giorni** (capienza max {max_pt_cap}h con max {max_h_day}h/giorno). Servono almeno **{min_days_needed} giorni** di presenza a scuola.")

            # Controllo giorni liberi part-time vs slot obbligatori
            f_days_names = getattr(t, "free_days", [])
            for fd_name in f_days_names:
                if fd_name in DAYS_OF_WEEK:
                    fd_idx = DAYS_OF_WEEK.index(fd_name)
                    # Verifica se ha lezioni fissate o slot di presenza tassativa nel giorno libero
                    req_in_fd = [s for s in getattr(t, "required_slots", []) if s[0] == fd_idx]
                    if req_in_fd:
                        issues.append(f"❌ **Docente Part-Time {t.name}**: impostati **{len(req_in_fd)} slot di presenza obbligatoria** il **{fd_name}**, che è indicato come Giorno Libero.")

        # C. Controllo slot obbligatori (Includi) e incompatibilità con Escludi
        req_slots = getattr(t, "required_slots", [])
        if len(req_slots) > t_h:
            issues.append(f"❌ **Docente {t.name}**: impostati **{len(req_slots)} slot di presenza obbligatoria** ma la cattedra è di sole **{t_h} ore**.")
        
        for r_s in req_slots:
            if r_s in getattr(t, "unavailable_slots", []):
                d_name = DAYS_OF_WEEK[r_s[0]] if r_s[0] < len(DAYS_OF_WEEK) else f"Giorno {r_s[0]+1}"
                issues.append(f"❌ **Docente {t.name}**: conflitto nello slot **{d_name} ({r_s[1]+1}ª ora)** impostato contemporaneamente sia come 'Escludi' che come 'Includi tassativo'.")

    # 3. Controllo Conflitti su Lezioni Prefissate / Bloccate (Pinned Slots)
    pinned_by_slot: Dict[Tuple[int, int], List[TeachingAssignment]] = {}
    pinned_by_teacher_slot: Dict[Tuple[str, int, int], List[TeachingAssignment]] = {}
    pinned_by_class_slot: Dict[Tuple[str, int, int], List[TeachingAssignment]] = {}
    
    for a in problem.assignments:
        for p_slot in getattr(a, "pinned_slots", []):
            if len(p_slot) == 2:
                d, h = p_slot[0], p_slot[1]
                slot_key = (d, h)
                pinned_by_slot.setdefault(slot_key, []).append(a)
                pinned_by_teacher_slot.setdefault((a.teacher_id, d, h), []).append(a)
                pinned_by_class_slot.setdefault((a.class_id, d, h), []).append(a)
                
                # Conflitto con indisponibilità docente
                t_obj = problem.teachers.get(a.teacher_id)
                if t_obj and [d, h] in getattr(t_obj, "unavailable_slots", []):
                    d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
                    issues.append(f"❌ **Conflitto Lezione Bloccata**: la lezione di **{t_obj.name}** per la classe **{a.class_id}** è bloccata il **{d_name} alla {h+1}ª ora**, ma il docente è contrassegnato come Indisponibile in quell'ora.")

    # Conflitto: stesso docente bloccato su 2 classi diverse nella stessa ora
    for (t_id, d, h), a_list in pinned_by_teacher_slot.items():
        if len(a_list) > 1:
            t_name = problem.teachers[t_id].name if t_id in problem.teachers else t_id
            d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
            c_names = ", ".join(problem.classes[a_item.class_id].name if a_item.class_id in problem.classes else a_item.class_id for a_item in a_list)
            issues.append(f"❌ **Conflitto Sovrapposizione Docente**: il docente **{t_name}** ha **{len(a_list)} lezioni bloccate** contemporaneamente il **{d_name} alla {h+1}ª ora** sulle classi: {c_names}.")

    # Conflitto: stessa classe con 2 materie diverse bloccate nella stessa ora
    for (c_id, d, h), a_list in pinned_by_class_slot.items():
        if len(a_list) > 1:
            c_name = problem.classes[c_id].name if c_id in problem.classes else c_id
            d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
            s_names = ", ".join(problem.subjects[a_item.subject_id].name if a_item.subject_id in problem.subjects else a_item.subject_id for a_item in a_list)
            issues.append(f"❌ **Conflitto Sovrapposizione Classe**: la classe **{c_name}** ha **{len(a_list)} materie bloccate** contemporaneamente il **{d_name} alla {h+1}ª ora** ({s_names}).")

    # 4. Controllo Capienza Aule Assegnate a Docenti, Laboratori e Spazi Dedicati
    # A. Controllo Aule con Docenti Assegnati Esclusivamente (100% Matching)
    for r_id, r in problem.rooms.items():
        if getattr(r, "teacher_ids", []):
            assigned_teachers = [t for t in r.teacher_ids if t in problem.teachers]
            if assigned_teachers:
                total_teachers_h = sum(
                    sum(a.hours_per_week for a in problem.assignments if a.teacher_id == t_id)
                    for t_id in assigned_teachers
                )
                room_max_cap_h = r.capacity * tot_slots
                if total_teachers_h > room_max_cap_h:
                    t_names = ", ".join(problem.teachers[t_id].name for t_id in assigned_teachers)
                    issues.append(
                        f"❌ **Aula {r.name} (Capienza {r.capacity})**: assegnata ai docenti ({t_names}) per un totale di **{total_teachers_h}h settimanali**, ma la capienza massima dell'aula è di sole **{room_max_cap_h}h**.\n"
                        f"   *(💡 Suggerimento: valuta se lavorare a **classi aperte** aumentando la capienza oppure dedicare un **secondo spazio**)*"
                    )

    # B. Controllo Capienza per Materia / Laboratori (Palestre, Arte, Musica, Teatro)
    room_group_req: Dict[Tuple[str, ...], int] = {}
    for a in problem.assignments:
        comp = []
        if a.preferred_room_id and a.preferred_room_id in problem.rooms:
            comp = [a.preferred_room_id]
        else:
            teacher_rooms = [r_id for r_id, r in problem.rooms.items() if a.teacher_id in getattr(r, "teacher_ids", []) and (not r.subject_ids or a.subject_id in r.subject_ids)]
            if teacher_rooms:
                comp = teacher_rooms
            else:
                comp = [r_id for r_id, r in problem.rooms.items() if (r.is_special_lab or r.subject_ids) and a.subject_id in r.subject_ids]
        if comp:
            comp_tuple = tuple(sorted(comp))
            room_group_req[comp_tuple] = room_group_req.get(comp_tuple, 0) + a.hours_per_week

    for comp_tuple, req_h in room_group_req.items():
        total_cap_h = sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms) * tot_slots
        if req_h > total_cap_h:
            names = ", ".join(problem.rooms[r_id].name for r_id in comp_tuple if r_id in problem.rooms)
            issues.append(
                f"❌ **Spazi/Laboratori ({names})**: richieste **{req_h} ore** settimanali ma la capienza massima disponibile è di **{total_cap_h} ore**.\n"
                f"   *(💡 Suggerimento: valuta se lavorare a **classi aperte** per queste classi oppure dedicare un **secondo spazio** a questa disciplina)*"
            )

    # 5. Controllo compatibilità accoppiamento a 2 ore
    for a in problem.assignments:
        if a.force_double_hours and a.hours_per_week == 1:
            issues.append(f"⚠️ **Cattedra {a.id} ({a.subject_id})**: forzata a blocco da 2h ma ha solo 1 ora settimanale.")

    # 6. Controllo Gruppi di Classi Aperte & Parallelismi Didattici
    for grp in getattr(problem.config, "parallel_groups", []):
        if not getattr(grp, "is_active", True):
            continue
        g_assigns = []
        for cid in grp.class_ids:
            matching = [a for a in problem.assignments if a.class_id == cid and a.subject_id == grp.subject_id]
            if matching:
                g_assigns.append(matching[0])
            else:
                c_name = problem.classes[cid].name if cid in problem.classes else cid
                s_name = problem.subjects[grp.subject_id].name if grp.subject_id in problem.subjects else grp.subject_id
                issues.append(f"❌ **Classi Aperte '{grp.name}'**: la classe **{c_name}** non ha cattedre assegnate per la materia **{s_name}**.")
        
        if len(g_assigns) >= 2:
            # Controllo docenti
            t_ids = [a.teacher_id for a in g_assigns]
            if len(set(t_ids)) < len(t_ids) and not getattr(grp, "is_same_teacher_merged", False):
                dup_t_names = [problem.teachers[tid].name for tid in t_ids if t_ids.count(tid) > 1 and tid in problem.teachers]
                dup_str = ", ".join(list(set(dup_t_names)))
                cl_names_str = ", ".join(problem.classes[c].name for c in grp.class_ids if c in problem.classes)
                issues.append(
                    f"❌ **Conflitto Docente su Classi Aperte '{grp.name}'**: il docente **{dup_str}** è assegnato a più classi contemporaneamente ({cl_names_str}).\n"
                    f"   *(💡 Un singolo docente non può fare lezione a classi separate nello stesso slot. Abilita 'Docente Unico Accorpato (Compresenza)' oppure accoppia classi con docenti diversi)*"
                )

            # Controllo capienza spazio condiviso se impostato
            if getattr(grp, "room_id", None) and grp.room_id in problem.rooms:
                r_obj = problem.rooms[grp.room_id]
                if r_obj.capacity < len(grp.class_ids):
                    issues.append(
                        f"⚠️ **Capienza Spazio Classi Aperte '{grp.name}'**: l'aula/palestra **{r_obj.name}** ha capienza {r_obj.capacity}, ma il gruppo comprende {len(grp.class_ids)} classi in contemporanea. La capienza dell'aula deve essere portata ad almeno {len(grp.class_ids)}."
                    )

    return issues

def get_room_bottlenecks(problem: TimetableProblem) -> List[Dict[str, Any]]:
    """Identifica con precisione i colli di bottiglia di aule e laboratori sovraffollati."""
    tot_slots = problem.config.total_weekly_slots
    bottlenecks = []
    
    # 1. Aule con docenti esclusivi
    for r_id, r in problem.rooms.items():
        if getattr(r, "teacher_ids", []):
            assigned_teachers = [t for t in r.teacher_ids if t in problem.teachers]
            if assigned_teachers:
                assigned_a = [a for a in problem.assignments if a.teacher_id in assigned_teachers]
                total_teachers_h = sum(a.hours_per_week for a in assigned_a)
                room_max_cap_h = r.capacity * tot_slots
                if total_teachers_h > room_max_cap_h:
                    bottlenecks.append({
                        "type": "teacher_room",
                        "room_ids": [r_id],
                        "primary_room_id": r_id,
                        "room_name": r.name,
                        "current_capacity": r.capacity,
                        "required_hours": total_teachers_h,
                        "available_hours": room_max_cap_h,
                        "excess_hours": total_teachers_h - room_max_cap_h,
                        "teacher_ids": assigned_teachers,
                        "subject_ids": list(set(a.subject_id for a in assigned_a)),
                        "class_ids": list(set(a.class_id for a in assigned_a)),
                        "assignments": assigned_a
                    })

    # 2. Laboratori per Materia
    room_group_req: Dict[Tuple[str, ...], List[TeachingAssignment]] = {}
    for a in problem.assignments:
        comp = []
        if a.preferred_room_id and a.preferred_room_id in problem.rooms:
            comp = [a.preferred_room_id]
        else:
            teacher_rooms = [r_id for r_id, r in problem.rooms.items() if a.teacher_id in getattr(r, "teacher_ids", []) and (not r.subject_ids or a.subject_id in r.subject_ids)]
            if teacher_rooms:
                comp = teacher_rooms
            else:
                comp = [r_id for r_id, r in problem.rooms.items() if (r.is_special_lab or r.subject_ids) and a.subject_id in r.subject_ids]
        if comp:
            comp_tuple = tuple(sorted(comp))
            room_group_req.setdefault(comp_tuple, []).append(a)

    for comp_tuple, a_list in room_group_req.items():
        req_h = sum(a.hours_per_week for a in a_list)
        total_cap_h = sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms) * tot_slots
        if req_h > total_cap_h:
            names = ", ".join(problem.rooms[r_id].name for r_id in comp_tuple if r_id in problem.rooms)
            existing = any(set(b["room_ids"]) == set(comp_tuple) for b in bottlenecks)
            if not existing:
                bottlenecks.append({
                    "type": "subject_lab",
                    "room_ids": list(comp_tuple),
                    "primary_room_id": comp_tuple[0],
                    "room_name": names,
                    "current_capacity": sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms),
                    "required_hours": req_h,
                    "available_hours": total_cap_h,
                    "excess_hours": req_h - total_cap_h,
                    "teacher_ids": list(set(a.teacher_id for a in a_list)),
                    "subject_ids": list(set(a.subject_id for a in a_list)),
                    "class_ids": list(set(a.class_id for a in a_list)),
                    "assignments": a_list
                })
    return bottlenecks

class TimetableSolver:
    def __init__(self, problem: TimetableProblem, max_gap_limit: int = 6, strict_gap_limit: bool = False):
        self.problem = problem
        self.cfg = problem.config
        self.num_days = self.cfg.num_days
        self.daily_hours = self.cfg.daily_hours[:self.num_days]
        self.max_gap_limit = max_gap_limit
        self.strict_gap_limit = strict_gap_limit
        self.model = cp_model.CpModel()
        
        # Variabili di decisione: (assignment_id, d, h) -> BoolVar
        self.x = {}
        
        # Variabili assegnazione aule: (assignment_id, room_id, d, h) -> BoolVar
        self.y_room = {}
        
        # Variabili presenza docente: (teacher_id, d, h) -> BoolVar
        self.t_active = {}
        self.t_day_active = {}
        self.t_gap = {}
        
        # Mappatura cattedra -> lista aule compatibili
        self.assignment_compatible_rooms: Dict[str, List[str]] = {}

    def _get_day_index(self, day_name: Optional[str]) -> Optional[int]:
        if not day_name:
            return None
        name_clean = day_name.strip().capitalize()
        for idx, d in enumerate(DAYS_OF_WEEK):
            if d.lower() == name_clean.lower():
                return idx
        return None

    def _determine_compatible_rooms(self):
        """Associa a ciascuna cattedra l'insieme ordinato di aule compatibili rispettando priorità e assegnazione docenti al 100%."""
        prob = self.problem
        is_dada = prob.config.is_dada

        for a in prob.assignments:
            comp_rooms = []
            subj = prob.subjects.get(a.subject_id)
            
            # 1. Aula specifica preferita o obbligatoria per questa cattedra
            if a.preferred_room_id and a.preferred_room_id in prob.rooms:
                comp_rooms = [a.preferred_room_id]
            else:
                # 2. Assegnazione aula a questo specifico docente (100% esaudita prioritariamente)
                teacher_rooms = [
                    r_id for r_id, r in prob.rooms.items()
                    if a.teacher_id in getattr(r, "teacher_ids", [])
                    and (not r.subject_ids or a.subject_id in r.subject_ids)
                ]
                if teacher_rooms:
                    # Ordina per priorità aula (1 = Massima priorità / Principale, 2 = Secondaria, 3 = Riserva)
                    teacher_rooms.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                    comp_rooms = teacher_rooms
                elif subj and subj.special_room_id and subj.special_room_id in prob.rooms:
                    comp_rooms = [subj.special_room_id]
                else:
                    # 3. Matching per materia:
                    # Se DADA: match su tutte le aule dedicate alla disciplina (ordinate per priorità)
                    # Se Tradizionale: match solo sui laboratori e aule speciali condivise (Palestre, Lab Arte, Musica, Tec)
                    if is_dada:
                        matching = [
                            r_id for r_id, r in prob.rooms.items()
                            if a.subject_id in r.subject_ids
                            and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                        ]
                        if matching:
                            matching.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                            comp_rooms = matching
                        else:
                            generic = [
                                r_id for r_id, r in prob.rooms.items()
                                if not r.is_special_lab and len(r.subject_ids) == 0
                                and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                            ]
                            if generic:
                                generic.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                                comp_rooms = generic
                    else:
                        matching_special = [
                            r_id for r_id, r in prob.rooms.items()
                            if r.is_special_lab and a.subject_id in r.subject_ids
                            and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                        ]
                        if matching_special:
                            matching_special.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                            comp_rooms = matching_special

            self.assignment_compatible_rooms[a.id] = comp_rooms

    def build_model(self, skip_penalties: bool = False):
        m = self.model
        prob = self.problem
        num_days = self.num_days
        daily_hours = self.daily_hours

        self._determine_compatible_rooms()

        # 1. Creazione variabili principali X[assignment, d, h]
        for a in prob.assignments:
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    var_name = f"x_{a.id}_d{d}_h{h}"
                    self.x[a.id, d, h] = m.NewBoolVar(var_name)

        # 2. VINCOLO RIGIDO: Monte ore settimanale esatto per ciascuna cattedra
        for a in prob.assignments:
            assigned_slots = [self.x[a.id, d, h] for d in range(num_days) for h in range(daily_hours[d])]
            m.Add(sum(assigned_slots) == a.hours_per_week)

        # 3. VINCOLO RIGIDO: Una classe può avere al massimo 1 lezione per ora
        for class_id in prob.classes:
            class_assignments = [a for a in prob.assignments if a.class_id == class_id]
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    slots = [self.x[a.id, d, h] for a in class_assignments]
                    m.Add(sum(slots) <= 1)

        # 4. Variabili e VINCOLO RIGIDO: Docenti (No sovrapposizioni)
        active_parallel_groups = [g for g in getattr(prob.config, "parallel_groups", []) if getattr(g, "is_active", True)]

        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    t_var = m.NewBoolVar(f"t_active_{t_id}_d{d}_h{h}")
                    self.t_active[t_id, d, h] = t_var
                    
                    # Gestione classi aperte con docente unico accorpato
                    merged_terms = []
                    accounted_a_ids = set()
                    for grp in active_parallel_groups:
                        if getattr(grp, "is_same_teacher_merged", False):
                            g_assigns = [a for a in t_assignments if a.class_id in grp.class_ids and a.subject_id == grp.subject_id]
                            if len(g_assigns) > 1:
                                merged_terms.append(self.x[g_assigns[0].id, d, h])
                                for ga in g_assigns:
                                    accounted_a_ids.add(ga.id)
                                    
                    remaining_slots = [self.x[a.id, d, h] for a in t_assignments if a.id not in accounted_a_ids]
                    all_t_terms = merged_terms + remaining_slots
                    if all_t_terms:
                        m.Add(sum(all_t_terms) == t_var)
                    else:
                        m.Add(t_var == 0)

        # 5. VINCOLO RIGIDO: Indisponibilità assoluta (Escludi) e Presenza Tassativa (Includi) dei Docenti
        for t_id, teacher in prob.teachers.items():
            # A. Escludi (Indisponibilità assoluta - NO Lezione)
            for slot in getattr(teacher, "unavailable_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(self.t_active[t_id, d, h] == 0)
            
            # B. Includi (Presenza Tassativa - DEVE avere Lezione)
            for slot in getattr(teacher, "required_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(self.t_active[t_id, d, h] == 1)

        # 5bis. VINCOLO RIGIDO: Pre-fissaggio Tassativo di Lezioni Specifiche (Classe + Materia nello Slot)
        for a in prob.assignments:
            for slot in getattr(a, "pinned_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(self.x[a.id, d, h] == 1)

        # 5ter. VINCOLO RIGIDO: Classi Aperte & Parallelismi Didattici (Sincronizzazione Oraria Perfetta)
        self.parallel_group_slot_vars = {}
        for g_idx, grp in enumerate(active_parallel_groups):
            group_assigns = []
            for cid in grp.class_ids:
                matching_a = [a for a in prob.assignments if a.class_id == cid and a.subject_id == grp.subject_id]
                if matching_a:
                    group_assigns.append(matching_a[0])
            
            if len(group_assigns) < 2:
                continue
                
            lead_a = group_assigns[0]
            follower_assigns = group_assigns[1:]
            p_hours = min(grp.parallel_hours, lead_a.hours_per_week)
            
            if p_hours >= lead_a.hours_per_week:
                # Sincronizzazione totale per tutte le ore della materia
                for other_a in follower_assigns:
                    for d in range(num_days):
                        for h in range(daily_hours[d]):
                            m.Add(self.x[lead_a.id, d, h] == self.x[other_a.id, d, h])
                self.parallel_group_slot_vars[grp.id] = None
            else:
                # Sincronizzazione parziale (es. 2h in parallelo su 5h di materia)
                p_slot_vars = {}
                for d in range(num_days):
                    for h in range(daily_hours[d]):
                        p_var = m.NewBoolVar(f"p_slot_{grp.id}_{g_idx}_d{d}_h{h}")
                        p_slot_vars[d, h] = p_var
                        for a_obj in group_assigns:
                            m.Add(self.x[a_obj.id, d, h] >= p_var)
                
                m.Add(sum(p_slot_vars.values()) == p_hours)
                self.parallel_group_slot_vars[grp.id] = p_slot_vars
                
                if grp.force_consecutive_block and p_hours == 2:
                    pair_vars = []
                    for d in range(num_days):
                        for h in range(daily_hours[d] - 1):
                            p_curr = p_slot_vars[d, h]
                            p_next = p_slot_vars[d, h+1]
                            pv = m.NewBoolVar(f"p_pair_{grp.id}_{g_idx}_d{d}_h{h}")
                            m.Add(pv <= p_curr)
                            m.Add(pv <= p_next)
                            m.Add(pv >= p_curr + p_next - 1)
                            pair_vars.append(pv)
                    m.Add(sum(pair_vars) == 1)

        # 6. VINCOLO RIGIDO: Capienza Massima Aule & Laboratori per Slot Orario
        # Raggruppa le cattedre per insieme di aule compatibili
        room_group_map: Dict[Tuple[str, ...], List[str]] = {}
        for a in prob.assignments:
            comp = tuple(sorted(self.assignment_compatible_rooms.get(a.id, [])))
            if comp:
                room_group_map.setdefault(comp, []).append(a.id)

        for comp_rooms_tuple, assign_ids in room_group_map.items():
            rooms_in_grp = [prob.rooms[r_id] for r_id in comp_rooms_tuple if r_id in prob.rooms]
            total_cap = sum(r.capacity for r in rooms_in_grp)
            
            # Identifica se ci sono gruppi paralleli attivi per questo gruppo di aule/materie
            room_pg_terms = []
            for grp in active_parallel_groups:
                g_assigns = [a for a in prob.assignments if a.class_id in grp.class_ids and a.subject_id == grp.subject_id]
                if g_assigns and any(a.id in assign_ids for a in g_assigns):
                    lead_a = g_assigns[0]
                    p_hours = min(grp.parallel_hours, lead_a.hours_per_week)
                    if p_hours >= lead_a.hours_per_week:
                        room_pg_terms.append((grp, lead_a.id, None))
                    else:
                        room_pg_terms.append((grp, None, self.parallel_group_slot_vars.get(grp.id, {})))
            
            total_h_needed = sum(prob.assignments_by_id[a_id].hours_per_week for a_id in assign_ids if hasattr(prob, "assignments_by_id") and a_id in prob.assignments_by_id) if hasattr(prob, "assignments_by_id") else sum(a.hours_per_week for a in prob.assignments if a.id in assign_ids)
            total_single_slots = sum(daily_hours[:num_days])
            excess_needed = max(0, total_h_needed - total_single_slots)

            for d in range(num_days):
                for h in range(daily_hours[d]):
                    active_in_slot = [self.x[a_id, d, h] for a_id in assign_ids]
                    
                    if total_cap > 1:
                        # Se ci sono gruppi paralleli, sblocca la capienza > 1 solo per i gruppi deliberati
                        pg_active_here = []
                        for grp, lead_aid, p_dict in room_pg_terms:
                            if lead_aid:
                                pg_active_here.append(self.x[lead_aid, d, h])
                            elif p_dict and (d, h) in p_dict:
                                pg_active_here.append(p_dict[d, h])
                        
                        if pg_active_here:
                            # La capienza massima nello slot è 1 + numero di gruppi paralleli attivi nello slot
                            m.Add(sum(active_in_slot) <= 1 + sum(pg_active_here))
                        else:
                            # Se non ci sono gruppi paralleli configurati ma le ore totali superano i 30 slot (excess_needed), permette capienza totale
                            if excess_needed == 0:
                                m.Add(sum(active_in_slot) <= 1)
                            else:
                                m.Add(sum(active_in_slot) <= total_cap)
                    else:
                        m.Add(sum(active_in_slot) <= total_cap)

        # 7. VINCOLO DIDATTICO RIGIDO: Max ore al giorno per materia in una classe
        # Regola tassativa: SOLO Italiano (se spuntato) può fare 3 ore di fila. TUTTE le altre materie hanno un tetto rigido di MAX 2 ORE al giorno.
        allow_triple_ita = getattr(prob.config, "allow_triple_hours_italian", False) or getattr(prob.config, "force_triple_hours_italian", False)
        for a in prob.assignments:
            is_ita = (a.subject_id == "ita" or "italian" in a.subject_id.lower())
            is_force_triple = is_ita and (getattr(prob.config, "force_triple_hours_italian", False) or getattr(a, "force_triple_hours", False))
            
            if is_ita and (allow_triple_ita or is_force_triple):
                eff_max_h = 3
            else:
                # Per qualsiasi altra materia (Matematica, Scienze, Lingue, ecc.) il massimo assoluto è 2 ore al giorno
                eff_max_h = min(a.max_daily_hours, 2)

            for d in range(num_days):
                daily_slots = [self.x[a.id, d, h] for h in range(daily_hours[d])]
                m.Add(sum(daily_slots) <= eff_max_h)

        # 7bis. VINCOLO DIDATTICO RIGIDO: Max ore al giorno per Docente nella stessa classe (MAI 4 ore per lo stesso docente in una classe nello stesso giorno!)
        for t_id, teacher in prob.teachers.items():
            for c_id in prob.classes:
                tc_assigns = [a for a in prob.assignments if a.teacher_id == t_id and a.class_id == c_id]
                if len(tc_assigns) > 1 or (tc_assigns and tc_assigns[0].hours_per_week >= 3):
                    for d in range(num_days):
                        tc_daily_slots = [self.x[a.id, d, h] for a in tc_assigns for h in range(daily_hours[d])]
                        m.Add(sum(tc_daily_slots) <= 3)

        # -------------------------------------------------------------
        # MODELLAZIONE SOFT CONSTRAINTS / DESIDERATA & FUNZIONE OBIETTIVO
        # -------------------------------------------------------------
        penalties = []

        # A. Variabile `t_day_active`: docente lavora nel giorno d & Regole Carico Giornaliero
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            t_total_h = sum(a.hours_per_week for a in t_assignments)

            for d in range(num_days):
                day_act = m.NewBoolVar(f"t_day_active_{t_id}_d{d}")
                self.t_day_active[t_id, d] = day_act
                day_slots = [self.t_active[t_id, d, h] for h in range(daily_hours[d])]
                m.AddMaxEquality(day_act, day_slots)

                # 1. MINIMO 2 ORE AL GIORNO (quando presente a scuola)
                min_daily_target = 2 if t_total_h >= 2 else t_total_h
                m.Add(sum(day_slots) >= min_daily_target).OnlyEnforceIf(day_act)
                m.Add(sum(day_slots) == 0).OnlyEnforceIf(day_act.Not())

                # 2. MASSIMO 5 ORE AL GIORNO
                m.Add(sum(day_slots) <= 5)

                # 3. MAX 4 ORE CONSECUTIVE: se fa 5 ore in un giorno, ci DEVE essere almeno un buco/pausa intermedia
                H = daily_hours[d]
                if H >= 5:
                    for h in range(H - 4):
                        m.Add(sum(self.t_active[t_id, d, h + k] for k in range(5)) <= 4)

            # 4. DOCENTI A TEMPO PIENO (18H su 5 giorni): SPALMATO TASSATIVAMENTE SU TUTTI I 5 GIORNI (Min 2h per giorno)
            if num_days == 5 and t_total_h >= 18 and not teacher.is_part_time:
                for d in range(5):
                    m.Add(self.t_day_active[t_id, d] == 1)

        criteria = getattr(prob.config, "optimization_criteria", None) or OptimizationCriteria()

        # B. DESIDERATA: Giorno Libero Docenti (Settimana corta vs lunga) & Vincolo Giorni Part-Time
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            t_total_h = sum(a.hours_per_week for a in t_assignments)
            
            # VINCOLO RIGIDO PART-TIME: Massimo N Giorni di presenza a scuola
            if teacher.is_part_time and teacher.max_working_days is not None:
                eff_max_d = max(teacher.max_daily_hours, 1)
                min_days_needed = (t_total_h + eff_max_d - 1) // eff_max_d if eff_max_d > 0 else 1
                allowed_max_days = max(teacher.max_working_days, min_days_needed)
                allowed_max_days = min(allowed_max_days, num_days)
                
                # Vincolo rigido: non può venire a scuola più giorni di quelli concordati
                m.Add(sum(self.t_day_active[t_id, d] for d in range(num_days)) <= allowed_max_days)

            can_have_free_day = (num_days == 6) or teacher.is_part_time or (t_total_h <= 14)
            
            if can_have_free_day and not skip_penalties:
                target_free_days = getattr(teacher, "free_days", [])
                if not target_free_days:
                    target_free_days = []
                    if teacher.free_day_1: target_free_days.append(teacher.free_day_1)
                    if teacher.free_day_2: target_free_days.append(teacher.free_day_2)

                for p_idx, fd_name in enumerate(target_free_days):
                    fd_idx = self._get_day_index(fd_name)
                    if fd_idx is not None:
                        w = 50 if p_idx == 0 else 25
                        penalties.append(self.t_day_active[t_id, fd_idx] * w)

        # C. DESIDERATA AVANZATI: Ingressi Posticipati & Uscite Anticipate (Pesi bilanciati per non frammentare l'orario)
        if not skip_penalties:
            for t_id, teacher in prob.teachers.items():
                l_days = getattr(teacher, "late_entry_days", [])
                if l_days:
                    for day_name in l_days:
                        d_idx = self._get_day_index(day_name)
                        if d_idx is not None and d_idx < num_days:
                            penalties.append(self.t_active[t_id, d_idx, 0] * 10)
                elif teacher.prefer_late_entry:
                    for d in range(num_days):
                        penalties.append(self.t_active[t_id, d, 0] * 5)

                e_days = getattr(teacher, "early_exit_days", [])
                if e_days:
                    for day_name in e_days:
                        d_idx = self._get_day_index(day_name)
                        if d_idx is not None and d_idx < num_days:
                            H = daily_hours[d_idx]
                            if H > 0:
                                penalties.append(self.t_active[t_id, d_idx, H - 1] * 10)
                elif teacher.prefer_early_exit:
                    for d in range(num_days):
                        H = daily_hours[d]
                        if H > 0:
                            penalties.append(self.t_active[t_id, d, H - 1] * 5)

        # D. DESIDERATA: Slot Sconsigliati (Evita se possibile)
        if not skip_penalties:
            for t_id, teacher in prob.teachers.items():
                for avoid_slot in getattr(teacher, "soft_avoid_slots", []):
                    if len(avoid_slot) == 2:
                        d_idx, h_idx = avoid_slot
                        if d_idx < num_days and h_idx < daily_hours[d_idx]:
                            penalties.append(self.t_active[t_id, d_idx, h_idx] * 15)

        # E. DESIDERATA DIDATTICO: Ore Doppie / Consecutività (Blocchi 2h e Blocco 3h Tema Italiano)
        force_triple_ita_school = getattr(prob.config, "force_triple_hours_italian", False)
        for a in prob.assignments:
            is_ita = (a.subject_id == "ita" or "italian" in a.subject_id.lower())
            is_force_triple = is_ita and (force_triple_ita_school or getattr(a, "force_triple_hours", False))

            if is_force_triple and a.hours_per_week >= 3:
                day_triplets = []
                for d in range(num_days):
                    H = daily_hours[d]
                    if H >= 3:
                        d_trips = []
                        for h in range(H - 2):
                            trip_var = m.NewBoolVar(f"trip_{a.id}_d{d}_h{h}")
                            m.AddBoolAnd([self.x[a.id, d, h], self.x[a.id, d, h + 1], self.x[a.id, d, h + 2]]).OnlyEnforceIf(trip_var)
                            d_trips.append(trip_var)
                        day_has_trip = m.NewBoolVar(f"d_trip_{a.id}_{d}")
                        m.AddMaxEquality(day_has_trip, d_trips)
                        day_triplets.append(day_has_trip)
                        
                        m.Add(sum(self.x[a.id, d, h] for h in range(H)) == 3).OnlyEnforceIf(day_has_trip)
                        m.Add(sum(self.x[a.id, d, h] for h in range(H)) <= 2).OnlyEnforceIf(day_has_trip.Not())

                if day_triplets:
                    m.Add(sum(day_triplets) == 1)
            else:
                is_force_double = a.force_double_hours
                if hasattr(prob.config, "subject_block_preferences") and prob.config.subject_block_preferences:
                    if a.subject_id in prob.config.subject_block_preferences:
                        is_force_double = bool(prob.config.subject_block_preferences[a.subject_id])

                if is_force_double and a.hours_per_week >= 2:
                    day_pairs = []
                    is_dada_strict_pairs = getattr(prob.config, "is_dada", False) and getattr(prob.config, "dada_strict_even_pairs", False)
                    for d in range(num_days):
                        H = daily_hours[d]
                        if H >= 2:
                            d_pairs = []
                            allowed_h_starts = [h for h in range(0, H - 1, 2)] if is_dada_strict_pairs else [h for h in range(H - 1)]
                            for h in allowed_h_starts:
                                pair_var = m.NewBoolVar(f"pair_{a.id}_d{d}_h{h}")
                                m.AddBoolAnd([self.x[a.id, d, h], self.x[a.id, d, h + 1]]).OnlyEnforceIf(pair_var)
                                d_pairs.append(pair_var)
                            day_has_pair = m.NewBoolVar(f"d_pair_{a.id}_{d}")
                            m.AddMaxEquality(day_has_pair, d_pairs)
                            day_pairs.append(day_has_pair)

                    if day_pairs:
                        # Se la materia è forzata a blocchi da 2 ore, accorpa TUTTE le ore possibili (es. 4h -> 2 blocchi da 2h, 6h -> 3 blocchi da 2h, 5h -> 2 blocchi da 2h + 1h)
                        target_pairs = a.hours_per_week // 2
                        m.Add(sum(day_pairs) == target_pairs)
                        
                        # In ogni giorno ci può essere al massimo 1 blocco da 2 ore per questa materia
                        for d in range(num_days):
                            m.Add(sum(self.x[a.id, d, h] for h in range(daily_hours[d])) <= 2)
                else:
                    if a.hours_per_week in [2, 3] and (a.max_daily_hours or 2) <= 1:
                        for d in range(num_days):
                            day_slots = [self.x[a.id, d, h] for h in range(daily_hours[d])]
                            m.Add(sum(day_slots) <= 1)

        # E-bis. MINIMIZZAZIONE USO SPAZI SECONDARI / EMERGENZA (Priorità Aule & Palestre)
        # Se un gruppo di aule contiene spazi a priorità differenziata (es. Palestra Principale Priorità 1 vs Emergenza Priorità 2),
        # penalizza l'uso di spazi secondari quando il numero di classi contemporanee eccede la capienza degli spazi di priorità superiore.
        if not skip_penalties:
            for comp_rooms_tuple, assign_ids in room_group_map.items():
                rooms_in_group = [prob.rooms[r_id] for r_id in comp_rooms_tuple if r_id in prob.rooms]
                prio1_cap = sum(r.capacity for r in rooms_in_group if getattr(r, "priority", 1) == 1)
                total_cap = sum(r.capacity for r in rooms_in_group)
                
                if 0 < prio1_cap < total_cap:
                    total_h_in_group = sum(prob.assignments_by_id[a_id].hours_per_week for a_id in assign_ids if hasattr(prob, "assignments_by_id") and a_id in prob.assignments_by_id) if hasattr(prob, "assignments_by_id") else sum(a.hours_per_week for a in prob.assignments if a.id in assign_ids)
                    total_slots = sum(daily_hours[:num_days])
                    min_overflow_needed = max(0, total_h_in_group - total_slots * prio1_cap)
                    
                    group_overflow_vars = []
                    for d in range(num_days):
                        for h in range(daily_hours[d]):
                            active_in_slot = [self.x[a_id, d, h] for a_id in assign_ids]
                            overflow_var = m.NewIntVar(0, total_cap - prio1_cap, f"overflow_prio_{abs(hash(comp_rooms_tuple))}_d{d}_h{h}")
                            m.Add(sum(active_in_slot) - prio1_cap <= overflow_var)
                            group_overflow_vars.append(overflow_var)
                            penalties.append(overflow_var * 1500)
                    
                    # Limita l'uso degli spazi secondari al minimo teorico assoluto (es. esattamente 6h per Muratori e 0h per Auditorium)
                    m.Add(sum(group_overflow_vars) == min_overflow_needed)

        # F. FORMULAZIONE BOOLEANA ULTRA-PERFORMANTE DELLE ORE BUCHE & EQUITÀ MIN-MAX
        if not skip_penalties:
            max_peak_gap = m.NewIntVar(0, 15, "max_peak_gap")
            strict = self.strict_gap_limit if self.strict_gap_limit is not None else criteria.strict_gap_limit
            user_max_gaps = int(self.max_gap_limit if self.max_gap_limit is not None else criteria.max_gap_limit)
            all_teacher_tot_gaps = []

            for t_id, teacher in prob.teachers.items():
                t_all_gaps = []
                for d in range(num_days):
                    H = daily_hours[d]
                    if H <= 2:
                        continue
                    
                    # Prefix booleans: has_before[h] <=> il docente ha almeno 1 ora prima dell'ora h
                    has_before = [None] * H
                    has_before[0] = m.NewConstant(0)
                    for h in range(1, H):
                        has_before[h] = m.NewBoolVar(f"hb_{t_id}_{d}_{h}")
                        m.AddMaxEquality(has_before[h], [has_before[h-1], self.t_active[t_id, d, h-1]])
                        
                    # Suffix booleans: has_after[h] <=> il docente ha almeno 1 ora dopo l'ora h
                    has_after = [None] * H
                    has_after[H-1] = m.NewConstant(0)
                    for h in range(H-2, -1, -1):
                        has_after[h] = m.NewBoolVar(f"ha_{t_id}_{d}_{h}")
                        m.AddMaxEquality(has_after[h], [has_after[h+1], self.t_active[t_id, d, h+1]])
                        
                    # Un'ora h è una buca se e solo se c'è lezione prima, lezione dopo, e ora h è vuota
                    d_gaps = []
                    for h in range(1, H-1):
                        is_gap = m.NewBoolVar(f"gap_{t_id}_{d}_{h}")
                        m.AddBoolAnd([has_before[h], has_after[h], self.t_active[t_id, d, h].Not()]).OnlyEnforceIf(is_gap)
                        m.AddBoolOr([has_before[h].Not(), has_after[h].Not(), self.t_active[t_id, d, h]]).OnlyEnforceIf(is_gap.Not())
                        t_all_gaps.append(is_gap)
                        d_gaps.append(is_gap)
                        penalties.append(is_gap * max(criteria.weight_gap_hours, 300))

                    # Vincolo strutturale: nello stesso giorno un docente NON può avere 2 o più ore buche
                    if len(d_gaps) >= 2 and strict:
                        m.Add(sum(d_gaps) <= 1)

                if t_all_gaps:
                    t_tot_gaps = m.NewIntVar(0, 30, f"tot_gaps_{t_id}")
                    m.Add(t_tot_gaps == sum(t_all_gaps))
                    all_teacher_tot_gaps.append(t_tot_gaps)
                    
                    # Blocca matematicamente il superamento del tetto massimo richiesto dall'utente
                    if strict:
                        m.Add(t_tot_gaps <= user_max_gaps)
                    
                    # Penalità progressiva per scoraggiare anche 1 o 2 buche e favorire l'azzeramento totale (0 buche)
                    gap_ov0 = m.NewIntVar(0, 30, f"gov0_{t_id}")
                    m.Add(gap_ov0 >= t_tot_gaps)
                    penalties.append(gap_ov0 * 500)

                    gap_ov1 = m.NewIntVar(0, 30, f"gov1_{t_id}")
                    m.Add(gap_ov1 >= t_tot_gaps - 1)
                    penalties.append(gap_ov1 * 1500)
                    
                    # Penalità se si supera il tetto morbido
                    if not strict:
                        gap_ov_max = m.NewIntVar(0, 30, f"govmax_{t_id}")
                        m.Add(gap_ov_max >= t_tot_gaps - user_max_gaps)
                        penalties.append(gap_ov_max * 5000)

            # Penalizza fortemente il picco massimo globale (Min-Max Fairness)
            if all_teacher_tot_gaps:
                for t_tot in all_teacher_tot_gaps:
                    m.Add(max_peak_gap >= t_tot)
                penalties.append(max_peak_gap * 10000)

            # Minimizza la somma di tutte le penalità
            if penalties:
                m.Minimize(sum(penalties))

    def solve(self, max_time_seconds: int = 45, random_seed: int = 42) -> TimetableResult:
        start_time = time.time()
        
        # -------------------------------------------------------------
        # RISOLUZIONE DIRETTA AD ALTA INTENSITÀ CP-SAT CON PROPAGAZIONE SAT
        # -------------------------------------------------------------
        self.model = cp_model.CpModel()
        self.x.clear()
        self.y_room.clear()
        self.t_active.clear()
        self.t_day_active.clear()
        self.t_gap.clear()
        self.build_model(skip_penalties=False)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_time_seconds
        solver.parameters.num_workers = 8
        solver.parameters.random_seed = random_seed
        solver.parameters.linearization_level = 1
        solver.parameters.symmetry_level = 2
        solver.parameters.cp_model_presolve = True
        
        status_code = solver.Solve(self.model)
        elapsed = time.time() - start_time
        
        status_map = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "INVALID",
            cp_model.UNKNOWN: "UNKNOWN"
        }
        status_str = status_map.get(status_code, "UNKNOWN")
        active_solver = solver
        
        # Fallback automatico intelligente se il vincolo rigido sulle buche blocca la fattibilità
        if status_str not in ["OPTIMAL", "FEASIBLE"] and (self.strict_gap_limit or getattr(self.problem.config.optimization_criteria, "strict_gap_limit", False)):
            backup_strict = self.strict_gap_limit
            self.strict_gap_limit = False
            self.model = cp_model.CpModel()
            self.x.clear()
            self.y_room.clear()
            self.t_active.clear()
            self.t_day_active.clear()
            self.t_gap.clear()
            self.build_model(skip_penalties=False)
            
            # Fallback veloce (max 10s) per vedere se ammorbidendo troviamo una soluzione subito
            solver.parameters.max_time_in_seconds = min(max_time_seconds, 10)
            status_code = solver.Solve(self.model)
            status_str = status_map.get(status_code, "UNKNOWN")
            active_solver = solver
            self.strict_gap_limit = backup_strict
            elapsed = time.time() - start_time

        res = TimetableResult(
            status=status_str,
            solve_time=round(elapsed, 2),
            objective_value=active_solver.ObjectiveValue() if status_str in ["OPTIMAL", "FEASIBLE"] else 0.0
        )
        
        if status_str not in ["OPTIMAL", "FEASIBLE"]:
            issues = diagnose_problem_feasibility(self.problem)
            user_max_gaps = int(self.max_gap_limit if self.max_gap_limit is not None else getattr(self.problem.config.optimization_criteria, "max_gap_limit", 5))
            strict = self.strict_gap_limit if self.strict_gap_limit is not None else getattr(self.problem.config.optimization_criteria, "strict_gap_limit", False)
            
            if strict:
                issues.append(f"🔒 **Vincolo Tassativo Ore Buche (max {user_max_gaps}h)**: Con {len(self.problem.classes)} classi e i vincoli attuali, un tetto rigido di {user_max_gaps}h potrebbe essere troppo restrittivo entro {max_time_seconds}s. Prova ad aumentare il tempo a disposizione o a rilassare leggermente il limite a {user_max_gaps + 1}h.")
            
            if issues:
                res.log_messages.extend(issues)
            else:
                res.log_messages.append(f"Il solutore ha restituito stato: {status_str}. Nessuna combinazione valida trovata entro il tempo limite di {max_time_seconds}s.")
            return res

        prob = self.problem
        num_days = self.num_days
        daily_hours = self.daily_hours
        
        for c_id in prob.classes:
            res.grid_by_class[c_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]
            
        for t_id in prob.teachers:
            res.grid_by_teacher[t_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]

        for r_id in prob.rooms:
            res.grid_by_room[r_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]

        # Assegnazione ordinata e coerente delle aule per ciascuno slot (d, h)
        # Mappa per garantire la continuità aula nei blocchi consecutivi (stessa aula per entrambe le ore del blocco da 2h)
        last_assigned_room_for_assignment = {}
        
        for d in range(num_days):
            for h in range(daily_hours[d]):
                occupied_rooms_in_slot = set()
                active_assigns_in_slot = [a for a in prob.assignments if active_solver.Value(self.x[a.id, d, h]) == 1]
                
                # Ordina: prima le cattedre che continuano dal blocco precedente per preservare la stessa aula
                def assignment_sort_key(a_obj):
                    prev_r = last_assigned_room_for_assignment.get(a_obj.id)
                    is_continuation = (h > 0 and prev_r is not None and active_solver.Value(self.x[a_obj.id, d, h-1]) == 1)
                    return (0 if is_continuation else 1, a_obj.id)

                active_assigns_in_slot.sort(key=assignment_sort_key)
                
                slot_info_list = []
                for a in active_assigns_in_slot:
                    subj = prob.subjects.get(a.subject_id)
                    teacher = prob.teachers.get(a.teacher_id)
                    school_class = prob.classes.get(a.class_id)
                    comp_rooms = self.assignment_compatible_rooms.get(a.id, [])
                    
                    assigned_room_id = None
                    assigned_room_name = None
                    
                    # 1. Continuità del blocco da 2h
                    if h > 0 and active_solver.Value(self.x[a.id, d, h-1]) == 1:
                        prev_room_id = last_assigned_room_for_assignment.get(a.id)
                        if prev_room_id and prev_room_id in prob.rooms:
                            cur_occ = sum(1 for (oa, occ_r_id, _) in slot_info_list if occ_r_id == prev_room_id)
                            if cur_occ < prob.rooms[prev_room_id].capacity:
                                assigned_room_id = prev_room_id
                                assigned_room_name = prob.rooms[prev_room_id].name
                    
                    # 2. Nuova assegnazione aula in base alla priorità e capienza
                    if assigned_room_id is None:
                        if comp_rooms:
                            sorted_comp = sorted(comp_rooms, key=lambda r_id: getattr(prob.rooms.get(r_id), "priority", 1) if r_id in prob.rooms else 1)
                            for r_id in sorted_comp:
                                if r_id in prob.rooms:
                                    cur_occ = sum(1 for (oa, occ_r_id, _) in slot_info_list if occ_r_id == r_id)
                                    if cur_occ < prob.rooms[r_id].capacity:
                                        assigned_room_id = r_id
                                        assigned_room_name = prob.rooms[r_id].name
                                        break
                        elif subj and subj.special_room_id and subj.special_room_id in prob.rooms:
                            assigned_room_id = subj.special_room_id
                            assigned_room_name = prob.rooms[subj.special_room_id].name

                    last_assigned_room_for_assignment[a.id] = assigned_room_id
                    co_t_names = [prob.teachers[ct].name for ct in a.co_teacher_ids if ct in prob.teachers]

                    slot_info = LessonSlotInfo(
                        assignment_id=a.id,
                        class_id=a.class_id,
                        class_name=school_class.name if school_class else a.class_id,
                        teacher_id=a.teacher_id,
                        teacher_name=teacher.name if teacher else a.teacher_id,
                        subject_id=a.subject_id,
                        subject_name=subj.name if subj else a.subject_id,
                        subject_color=subj.color if subj else "#3498db",
                        room_id=assigned_room_id,
                        room_name=assigned_room_name,
                        co_teachers=co_t_names
                    )
                    slot_info_list.append((a, assigned_room_id, slot_info))

                # Post-processing per identificare le compresenze (co-docenti, classi aperte, condivisione aula)
                active_parallel_groups = [pg for pg in getattr(prob.config, "parallel_groups", []) if pg.is_active]
                for a_item, r_id, s_info in slot_info_list:
                    comp_desc_parts = []
                    
                    # 1. Co-docenti su stessa cattedra (es. sostegno / ITP)
                    if s_info.co_teachers:
                        s_info.is_compresenza = True
                        comp_desc_parts.append(f"Compresenza con {', '.join(s_info.co_teachers)}")
                        
                    # 2. Gruppi di Classi Aperte / Parallelismi
                    for grp in active_parallel_groups:
                        if a_item.class_id in grp.class_ids and a_item.subject_id == grp.subject_id:
                            is_group_parallel_slot = False
                            p_vars = getattr(self, "parallel_group_slot_vars", {}).get(grp.id)
                            if p_vars is not None:
                                if (d, h) in p_vars and active_solver.Value(p_vars[d, h]) == 1:
                                    is_group_parallel_slot = True
                            else:
                                other_in_grp = [
                                    (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                    if oa.class_id in grp.class_ids and oa.class_id != a_item.class_id and oa.subject_id == grp.subject_id
                                ]
                                if len(other_in_grp) == len(grp.class_ids) - 1:
                                    is_group_parallel_slot = True

                            if is_group_parallel_slot:
                                other_active_in_grp = [
                                    (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                    if oa.class_id in grp.class_ids and oa.class_id != a_item.class_id and oa.subject_id == grp.subject_id
                                ]
                                if other_active_in_grp:
                                    s_info.is_compresenza = True
                                    other_c_names = [os_info.class_name for (_, _, os_info) in other_active_in_grp]
                                    other_t_names = [os_info.teacher_name for (_, _, os_info) in other_active_in_grp if os_info.teacher_id != s_info.teacher_id]
                                    s_info.parallel_classes = other_c_names
                                    s_info.parallel_teachers = other_t_names
                                    
                                    if other_t_names:
                                        comp_desc_parts.append(f"Classi Aperte con {', '.join(other_c_names)} ({', '.join(other_t_names)})")
                                    else:
                                        comp_desc_parts.append(f"Classi Aperte con {', '.join(other_c_names)}")
                                    
                    # 3. Stessa Aula / Palestra condivisa con altre classi nello stesso momento
                    if r_id and r_id in prob.rooms:
                        room_obj = prob.rooms[r_id]
                        if room_obj.capacity > 1 or room_obj.is_special_lab or "palestra" in r_id.lower() or "palestra" in room_obj.name.lower():
                            same_room_other = [
                                (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                if occ_r == r_id and oa.id != a_item.id and (oa.class_id not in s_info.parallel_classes)
                            ]
                            if same_room_other:
                                s_info.is_compresenza = True
                                other_c_names = [os_info.class_name for (_, _, os_info) in same_room_other]
                                other_t_names = [os_info.teacher_name for (_, _, os_info) in same_room_other if os_info.teacher_id != s_info.teacher_id]
                                if other_t_names:
                                    comp_desc_parts.append(f"Spazio {s_info.room_name} con {', '.join(other_c_names)} ({', '.join(other_t_names)})")
                                else:
                                    comp_desc_parts.append(f"Spazio {s_info.room_name} con {', '.join(other_c_names)}")
                                
                    if comp_desc_parts:
                        s_info.compresenza_text = " | ".join(comp_desc_parts)

                    # Inserimento nelle griglie
                    res.grid_by_class[a_item.class_id][d][h] = s_info
                    res.grid_by_teacher[a_item.teacher_id][d][h] = s_info
                    
                    for ct_id in a_item.co_teacher_ids:
                        if ct_id in res.grid_by_teacher:
                            res.grid_by_teacher[ct_id][d][h] = s_info

                # Popolamento griglia per Aula/Spazio
                for r_id_key in prob.rooms:
                    room_slots = [(oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list if occ_r == r_id_key]
                    if len(room_slots) == 1:
                        res.grid_by_room[r_id_key][d][h] = room_slots[0][2]
                    elif len(room_slots) > 1:
                        all_c_names = " + ".join([os_info.class_name for (_, _, os_info) in room_slots])
                        all_t_names = " + ".join(list(dict.fromkeys([os_info.teacher_name for (_, _, os_info) in room_slots])))
                        s_first = room_slots[0][2]
                        combined_room_slot = LessonSlotInfo(
                            assignment_id=s_first.assignment_id,
                            class_id="compresenza",
                            class_name=f"{all_c_names}",
                            teacher_id="compresenza",
                            teacher_name=f"{all_t_names}",
                            subject_id=s_first.subject_id,
                            subject_name=s_first.subject_name,
                            subject_color=s_first.subject_color,
                            room_id=r_id_key,
                            room_name=s_first.room_name,
                            is_compresenza=True,
                            compresenza_text=f"Compresenza ({len(room_slots)} Classi in contemporanea)"
                        )
                        res.grid_by_room[r_id_key][d][h] = combined_room_slot

        # ---------------------------------------------------------
        # Calcolo Statistiche sui Desiderata
        # ---------------------------------------------------------
        # 1. Giorno Libero
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            t_total_h = sum(a.hours_per_week for a in t_assignments)
            can_have_free_day = (num_days == 6) or teacher.is_part_time or (t_total_h <= 14)
            
            if can_have_free_day:
                fd1 = self._get_day_index(teacher.free_day_1)
                if fd1 is not None:
                    res.free_days_total_first += 1
                    if active_solver.Value(self.t_day_active[t_id, fd1]) == 0:
                        res.free_days_satisfied_first += 1
                        
                fd2 = self._get_day_index(teacher.free_day_2)
                if fd2 is not None:
                    res.free_days_total_second += 1
                    if active_solver.Value(self.t_day_active[t_id, fd2]) == 0:
                        res.free_days_satisfied_second += 1

        # 2. Ore Buche calcolate direttamente dalla griglia oraria effettiva
        total_gaps = 0
        for t_id, teacher in prob.teachers.items():
            t_gaps = 0
            t_grid = res.grid_by_teacher.get(t_id, [])
            for d in range(num_days):
                active_hours = [h for h in range(daily_hours[d]) if t_grid and d < len(t_grid) and h < len(t_grid[d]) and t_grid[d][h] is not None]
                if len(active_hours) >= 2:
                    first_h = min(active_hours)
                    last_h = max(active_hours)
                    span = last_h - first_h + 1
                    worked = len(active_hours)
                    t_gaps += (span - worked)
            res.gaps_by_teacher[t_id] = t_gaps
            total_gaps += t_gaps
        res.total_gap_hours = total_gaps

        # 3. Ore doppie verificate per singola materia flaggata nel Tab Configurazione
        res.double_hours_by_subject = {}
        for s_id, s in prob.subjects.items():
            is_flagged = False
            if hasattr(prob.config, "subject_block_preferences") and prob.config.subject_block_preferences:
                is_flagged = bool(prob.config.subject_block_preferences.get(s_id, False))
            
            s_assigns = [a for a in prob.assignments if a.subject_id == s_id and a.hours_per_week >= 2]
            if not s_assigns:
                continue
                
            sat_count = 0
            tot_count = len(s_assigns)
            
            for a in s_assigns:
                has_adj = False
                for d in range(num_days):
                    for h in range(daily_hours[d] - 1):
                        if active_solver.Value(self.x[a.id, d, h]) == 1 and active_solver.Value(self.x[a.id, d, h + 1]) == 1:
                            has_adj = True
                            break
                    if has_adj:
                        break
                if has_adj:
                    sat_count += 1
                    
            pct = round(sat_count / tot_count * 100) if tot_count > 0 else 100
            res.double_hours_by_subject[s_id] = {
                "name": s.name,
                "is_flagged": is_flagged,
                "total": tot_count,
                "satisfied": sat_count,
                "pct": pct
            }
            if is_flagged:
                res.double_hours_total += tot_count
                res.double_hours_satisfied += sat_count

        # 4. Desiderata Avanzati (Entrare tardi / Uscire presto / Slot puntuali)
        for t_id, teacher in prob.teachers.items():
            # Ingressi posticipati (No 1ª ora nei giorni specificati)
            l_days = getattr(teacher, "late_entry_days", [])
            if l_days:
                for day_name in l_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and d_idx < num_days:
                        res.late_entry_total += 1
                        if active_solver.Value(self.t_active[t_id, d_idx, 0]) == 0:
                            res.late_entry_satisfied += 1
            elif teacher.prefer_late_entry:
                res.late_entry_total += 1
                if any(active_solver.Value(self.t_active[t_id, d, 0]) == 0 for d in range(num_days)):
                    res.late_entry_satisfied += 1

            # Uscite anticipate (No ultima ora nei giorni specificati)
            e_days = getattr(teacher, "early_exit_days", [])
            if e_days:
                for day_name in e_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and d_idx < num_days:
                        H = daily_hours[d_idx]
                        if H > 0:
                            res.early_exit_total += 1
                            if active_solver.Value(self.t_active[t_id, d_idx, H - 1]) == 0:
                                res.early_exit_satisfied += 1
            elif teacher.prefer_early_exit:
                res.early_exit_total += 1
                if any(daily_hours[d] > 0 and active_solver.Value(self.t_active[t_id, d, daily_hours[d] - 1]) == 0 for d in range(num_days)):
                    res.early_exit_satisfied += 1

            # Slot puntuali sconsigliati
            for slot in teacher.soft_avoid_slots:
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        res.soft_slots_total += 1
                        if active_solver.Value(self.t_active[t_id, d, h]) == 0:
                            res.soft_slots_satisfied += 1

        # 5. Generazione Report di Soddisfazione Dettagliato per Docente
        teacher_reports = {}
        total_scores = []
        for t_id, teacher in prob.teachers.items():
            t_grid = res.grid_by_teacher.get(t_id, [])
            
            # Calcolo giorni effettivi di presenza
            active_d_indices = []
            for d in range(num_days):
                if any(t_grid[d][h] is not None for h in range(daily_hours[d])):
                    active_d_indices.append(d)
            
            assigned_free_days = [DAYS_OF_WEEK[d] for d in range(num_days) if d not in active_d_indices]
            
            # Desiderata Giorno Libero
            req_fds = getattr(teacher, "free_days", [])
            if not req_fds:
                req_fds = []
                if teacher.free_day_1: req_fds.append(teacher.free_day_1)
                if teacher.free_day_2: req_fds.append(teacher.free_day_2)
                
            can_have_fd = (num_days == 6) or teacher.is_part_time
            fd_status = "N/A (Tempo pieno 5gg)"
            fd_satisfied_count = 0
            if can_have_fd:
                if req_fds:
                    satisfied_fds = [d for d in req_fds if d in assigned_free_days]
                    fd_satisfied_count = len(satisfied_fds)
                    if fd_satisfied_count == len(req_fds):
                        fd_status = f"✅ 100% Concesso ({', '.join(satisfied_fds)})"
                    elif fd_satisfied_count > 0:
                        fd_status = f"🟡 Parziale ({', '.join(satisfied_fds)} su {', '.join(req_fds)})"
                    else:
                        fd_status = f"❌ Non concesso (Assegnato: {', '.join(assigned_free_days) if assigned_free_days else 'Nessuno'})"
                else:
                    fd_status = f"ℹ️ Assegnato: {', '.join(assigned_free_days) if assigned_free_days else 'Nessuno'}"
            
            # Ingressi posticipati (No 1ª ora nei giorni specificati)
            late_entry_ok = 0
            late_entry_total = 0
            l_days = getattr(teacher, "late_entry_days", [])
            if l_days:
                late_entry_total = len(l_days)
                for day_name in l_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and solver.Value(self.t_active[t_id, d_idx, 0]) == 0:
                        late_entry_ok += 1
            elif teacher.prefer_late_entry:
                late_entry_total = 1
                if any(solver.Value(self.t_active[t_id, d, 0]) == 0 for d in active_d_indices):
                    late_entry_ok = 1

            # Uscite anticipate (No ult. ora nei giorni specificati)
            early_exit_ok = 0
            early_exit_total = 0
            e_days = getattr(teacher, "early_exit_days", [])
            if e_days:
                early_exit_total = len(e_days)
                for day_name in e_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None:
                        H = daily_hours[d_idx]
                        if H > 0 and solver.Value(self.t_active[t_id, d_idx, H - 1]) == 0:
                            early_exit_ok += 1
            elif teacher.prefer_early_exit:
                early_exit_total = 1
                if any(daily_hours[d] > 0 and solver.Value(self.t_active[t_id, d, daily_hours[d] - 1]) == 0 for d in active_d_indices):
                    early_exit_ok = 1

            # Ore buche del docente
            t_gaps = res.gaps_by_teacher.get(t_id, 0)
            
            # Slot puntuali sconsigliati
            soft_slots_ok = 0
            soft_slots_total = len(teacher.soft_avoid_slots)
            for slot in teacher.soft_avoid_slots:
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        if solver.Value(self.t_active[t_id, d, h]) == 0:
                            soft_slots_ok += 1

            # Ore doppie relative al docente
            t_double_ok = 0
            t_double_total = 0
            for a in prob.assignments:
                if (a.teacher_id == t_id or t_id in a.co_teacher_ids) and a.force_double_hours:
                    t_double_total += 1
                    for d in range(num_days):
                        for h in range(daily_hours[d] - 1):
                            if solver.Value(self.x[a.id, d, h]) == 1 and solver.Value(self.x[a.id, d, h + 1]) == 1:
                                t_double_ok += 1
                                break

            # Calcolo Punteggio % Soddisfazione (0 - 100)
            score_points = 100.0
            
            if can_have_fd and req_fds:
                if fd_satisfied_count == 0:
                    score_points -= 25.0
                elif fd_satisfied_count < len(req_fds):
                    score_points -= 10.0
                    
            if late_entry_total > 0:
                late_ratio = late_entry_ok / late_entry_total
                score_points -= (1.0 - late_ratio) * 15.0
                
            if early_exit_total > 0:
                early_ratio = early_exit_ok / early_exit_total
                score_points -= (1.0 - early_ratio) * 15.0
                
            if soft_slots_total > 0:
                soft_ratio = soft_slots_ok / soft_slots_total
                score_points -= (1.0 - soft_ratio) * 20.0
                
            if t_gaps > teacher.max_gap_hours:
                score_points -= min(25.0, (t_gaps - teacher.max_gap_hours) * 10.0)
            elif t_gaps > 0:
                score_points -= min(10.0, t_gaps * 3.0)

            score_final = max(0.0, min(100.0, score_points))
            total_scores.append(score_final)
            
            if score_final >= 90:
                status_badge = "🟢 100% Soddisfatto" if score_final >= 99 else f"🟢 Ottimo ({int(score_final)}%)"
            elif score_final >= 70:
                status_badge = f"🟡 Buono ({int(score_final)}%)"
            else:
                status_badge = f"🔴 Da Verificare ({int(score_final)}%)"

            teacher_reports[t_id] = {
                "name": teacher.name,
                "cdc": getattr(teacher, "cdc", ""),
                "is_part_time": teacher.is_part_time,
                "contract_hours": getattr(teacher, "contract_hours", 18),
                "working_days_count": len(active_d_indices),
                "assigned_free_days": assigned_free_days,
                "requested_free_days": req_fds,
                "free_day_status": fd_status,
                "prefer_late_entry": teacher.prefer_late_entry,
                "late_entry_result": f"{late_entry_ok}/{late_entry_total} gg" if late_entry_total > 0 else "-",
                "prefer_early_exit": teacher.prefer_early_exit,
                "early_exit_result": f"{early_exit_ok}/{early_exit_total} gg" if early_exit_total > 0 else "-",
                "gap_hours": t_gaps,
                "soft_slots_result": f"{soft_slots_ok}/{soft_slots_total}" if soft_slots_total > 0 else "-",
                "double_hours_result": f"{t_double_ok}/{t_double_total}" if t_double_total > 0 else "-",
                "score_percent": round(score_final, 1),
                "status_badge": status_badge
            }

        res.teacher_reports = teacher_reports
        res.global_satisfaction_score = round(sum(total_scores) / len(total_scores), 1) if total_scores else 100.0

        return res
